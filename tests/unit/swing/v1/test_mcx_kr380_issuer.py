"""Isolated close-cross qualification; none of these facts commission MCX."""

from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kronos.swing.v1.mcx_contract_profile import McxFamily, mcx_unit_profile
from kronos.swing.v1.mcx_kr380_issuer import (
    McxContinuityProof, McxCurrentAuthority, McxIsolatedEntryPolicy, McxKr380ReadSet,
    McxKr380Rejected, McxOneHourCandle, issue_isolated_mcx_kr380,
)
from kronos.swing.v1.mcx_production_entry import McxExactContractProof
from kronos.swing.v1.mcx_trade_plan import (
    MCX_V1_ADVISORY_AUTHORITY, MCX_TRADE_PLAN_CONTRACT, McxTradePlanRecord,
    McxTradeSetup, _digest as plan_digest,
)
from kronos.swing.v1.mcx_step31_construction import McxQuantitySemantics
from kronos.swing.v1.mcx_v1_advisory import LocalMcxV1AdvisoryStore
from kronos.swing.v1.mcx_v1_issuer import (
    McxV1SignalReadSet, issue_v1_isolated_signal,
)
from kronos.swing.v1.native_discovery import NativeOpportunityIdentity
from kronos.swing.v1.models import V1Direction
from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.v1.native_entry_timing import (
    ECPC_CONTRACT_ID, ECPC_VERSION, EcpcV2Outcome,
    LocalKr380V2Store, NativeEcpcV2Context, _values_digest,
)
from kronos.swing.v1.step32 import (
    CONTRACT_VERSION, RISK_APPROVAL_CONTRACT_ID, RiskApproval,
    RiskConstraints, RiskState,
)
from kronos.swing.v1.trade_construction import TradeCandidateIntegrity


IST = ZoneInfo("Asia/Kolkata")
START = datetime(2026, 9, 29, 10, tzinfo=IST)
HASH = "a" * 64


def _fixture(family=McxFamily.GOLDM, direction="LONG"):
    profile = mcx_unit_profile(family)  # Illustrative geometry; not authenticated authority.
    multiplier = profile.quotation_multiplier_per_lot
    entry = Decimal("100")
    stop = Decimal("95") if direction == "LONG" else Decimal("105")
    target = Decimal("110") if direction == "LONG" else Decimal("90")
    previous_close = Decimal("99") if direction == "LONG" else Decimal("101")
    current_close = Decimal("101") if direction == "LONG" else Decimal("99")
    symbol = family.value + "26OCTFUT"
    proof = McxExactContractProof(
        family=family, run_identity="ISOLATED-RUN", selected_contract=symbol,
        selected_expiry="2026-10-28", selection_sha256=HASH,
        handoff_sha256=HASH, review_receipt_identity="RECEIPT-1",
        review_receipt_sha256=HASH, v2_identity="V2-1", v2_sha256=HASH,
        master_snapshot_identity="SNAPSHOT-1", master_record_identity="RECORD-1",
        master_token=1234, master_file_sha256=HASH,
        specification_sha256=HASH, conversion_sha256=HASH,
        exchange_cutoff_sha256=HASH, broker_cutoff_sha256=HASH,
        completed_daily_sha256=HASH, completed_four_hour_sha256=HASH,
        completed_one_hour_sha256=HASH, completed_series_sha256=HASH,
        completed_daily_boundary=START-timedelta(days=1),
        completed_four_hour_boundary=START-timedelta(hours=1),
        completed_one_hour_boundary=START+timedelta(hours=1),
        lots=1, physical_quantity=profile.trading_quantity,
        physical_unit=profile.trading_unit,
        provider_order_quantity=1, provider_order_unit="LOTS",
        price_to_rupee_multiplier=multiplier, gross_notional=entry*multiplier,
        rupees_per_tick=profile.tick_in_quotation_units*multiplier,
        gross_stop_risk=abs(entry-stop)*multiplier,
        fees=None, margin=None, missing_authority=(), read_set_sha256=HASH,
    )
    risk = RiskApproval(
        RISK_APPROVAL_CONTRACT_ID, CONTRACT_VERSION, "RISK-1", "PLAN-1",
        HASH, "JUDGMENT-1", "ISOLATED-RUN", RiskState.APPROVED,
        RiskConstraints(), "ISOLATED_FIXTURE", START, START+timedelta(hours=5),
        ("ISOLATED",), TradeCandidateIntegrity.VALID,
    )
    ecpc = dict(
        context_identity="ECPC-1", native_run_identity="ISOLATED-RUN",
        canonical_instrument=family.value, direction=direction,
        trade_plan_id="PLAN-1", trade_plan_sha256=HASH, risk_result_id="RISK-1",
        monitoring_binding_id="MONITOR-1", session_identity="MCX-20260929",
        observation_boundary=START+timedelta(hours=2),
        outcome=EcpcV2Outcome.QUALIFIED, blockers=(), provenance=("ISOLATED",),
        contract_identity=ECPC_CONTRACT_ID, contract_version=ECPC_VERSION,
    )
    context = NativeEcpcV2Context(integrity_sha256=_values_digest(ecpc), **ecpc)
    common = dict(run_identity="ISOLATED-RUN", family=family,
                  trading_symbol=symbol, expiry="2026-10-28", provider_token=1234,
                  session_identity="MCX-20260929", revision=1,
                  source_sha256=HASH, confirmed_complete=True)
    previous = McxOneHourCandle(
        **common, candle_identity="CANDLE-P", source_sequence=1,
        opened_at=START, closed_at=START+timedelta(hours=1),
        open=previous_close, high=previous_close+1, low=previous_close-1,
        close=previous_close,
    )
    current = McxOneHourCandle(
        **common, candle_identity="CANDLE-C", source_sequence=2,
        opened_at=previous.closed_at, closed_at=START+timedelta(hours=2),
        open=previous_close, high=max(previous_close,current_close)+1,
        low=min(previous_close,current_close)-1, close=current_close,
    )
    continuity = McxContinuityProof(
        previous.candle_identity, previous.revision, previous.source_sha256,
        current.candle_identity, current.revision, current.source_sha256,
        current.session_identity, True, True, True, "GAP-PROOF-1", HASH,
    )
    policy = McxIsolatedEntryPolicy(
        "ISOLATED-POLICY", HASH, proof.gross_stop_risk,
        START+timedelta(hours=4), START+timedelta(hours=3), HASH, HASH,
    )
    authority = McxCurrentAuthority(
        proof.run_identity, proof.selected_contract, proof.selected_expiry,
        proof.master_token, proof.selection_sha256,
        proof.review_receipt_identity, proof.review_receipt_sha256,
        proof.v2_identity, proof.v2_sha256, proof.read_set_sha256,
    )
    return McxKr380ReadSet(
        proof, risk, context, previous, current, continuity, policy, authority,
        "PLAN-1", HASH, "KR370-1", "MONITOR-1", direction,
        entry, stop, target, profile.tick_in_quotation_units,
    )


def _v1_fixture(family=McxFamily.GOLDM, direction="LONG"):
    old = _fixture(family, direction)
    schedule = MarketCalendarPublisher().schedule(
        "MCX", START.date(), observed_at=START)
    p = replace(old.previous, session_identity=schedule.session_identity)
    c = replace(old.current, session_identity=schedule.session_identity)
    continuity = replace(old.continuity,
                         session_identity=schedule.session_identity)
    values = dict(
        trade_plan_id="", native_run_identity=p.run_identity,
        native_opportunity_identity=NativeOpportunityIdentity.ESTABLISHED_TREND_RESUMPTION,
        canonical_instrument=family.value,
        native_direction=V1Direction(direction),
        readiness_record_identity="KR370-1",
        observation_boundary=p.closed_at,
        setup_identity=McxTradeSetup.ONE_HOUR_RESUMPTION,
        entry=old.entry, stop=old.stop,
        invalidation_reference=old.stop,
        invalidation_condition="COMPLETED_MCX_1H_CLOSE_BEYOND_STOP",
        canonical_target=old.target, risk_reward_ratio=Decimal("2"),
        execution_context_identity="RECORD-1", family=family,
        contract_symbol=p.trading_symbol, expiry=p.expiry,
        entry_eligibility_boundary=c.closed_at + timedelta(hours=3),
        manifest_sha256=HASH, assessment_sha256=HASH,
        selection_sha256=HASH, handoff_integrity_sha256=HASH,
        receipt_integrity_sha256=HASH, promotion_integrity_sha256=HASH,
        completed_one_hour_sha256=p.source_sha256,
        provider_record_identity="RECORD-1",
        provider_snapshot_identity="SNAPSHOT-1",
        normalized_instrument_sha256=HASH,
        effective_specification_sha256=None,
        quote_quantity_per_lot=None, quantity=None,
        provider_quantity_semantics=McxQuantitySemantics.UNKNOWN,
        expiry_session_identity=schedule.session_identity,
        entry_blackout_policy_identity="UNKNOWN",
        one_hour_invalidation_policy_identity="MCX_COMPLETED_1H",
        sponsor_risk_policy_identity="MCX_V1_ADVISORY_NO_NUMERIC_CEILING",
        paper_choice_policy_identity="ONE_VERIFIED_CONTRACT_LOT",
        maximum_stop_risk=None, margin_policy_identity="UNKNOWN",
        created_at=p.closed_at + timedelta(seconds=1),
        integrity_hash="", contract_identity=MCX_TRADE_PLAN_CONTRACT,
        contract_version="1", authority=MCX_V1_ADVISORY_AUTHORITY,
    )
    values["trade_plan_id"] = "MCX-TRADE-PLAN-" + plan_digest(values)
    values["integrity_hash"] = plan_digest(values)
    plan = McxTradePlanRecord(**values)
    risk = replace(old.risk, candidate_id=plan.trade_plan_id,
                   candidate_digest=plan.integrity_hash,
                   state=RiskState.UNAVAILABLE, reason="RUPEE_MULTIPLIER_UNKNOWN")
    return McxV1SignalReadSet(
        plan, risk, p, c, continuity,
        replace(old.current_authority,
                run_identity=plan.native_run_identity,
                contract_symbol=plan.contract_symbol,
                expiry=plan.expiry),
        schedule, "MONITOR-1", Decimal("1"),
    )


@pytest.mark.parametrize("family", list(McxFamily))
@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_v1_five_family_completed_close_signal_without_monetary_guess(
    tmp_path, family, direction,
):
    read = _v1_fixture(family, direction)
    store = LocalMcxV1AdvisoryStore(tmp_path / "v1-outcomes")
    kwargs = dict(evaluated_at=read.current.closed_at,
                  store=store, commit_guard=nullcontext,
                  guarded_recheck=lambda _digest: True)
    first = issue_v1_isolated_signal(lambda: read, **kwargs)
    assert first.state.value == direction + "_ADVISORY_CONFIRMED"
    assert first.broker_authority == "NONE"
    assert issue_v1_isolated_signal(lambda: read, **kwargs) == first
    assert store.load_for_plan(read.plan.trade_plan_id) == first


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_v1_advisory_equality_and_unverified_intrabar_are_not_p32(tmp_path, direction):
    from kronos.swing.v1.native_entry_timing import Kr380EntryOutcomeV2
    from kronos.swing.v1.mcx_v1_advisory import ADVISORY_SCHEMA
    read = _v1_fixture(direction=direction)
    read = replace(read, current=replace(read.current, close=read.plan.entry),
                   continuity=replace(read.continuity, no_entry_spanning_gap=False))
    outcome = issue_v1_isolated_signal(
        lambda: read, evaluated_at=read.current.closed_at,
        store=LocalMcxV1AdvisoryStore(tmp_path / "advice"),
        commit_guard=nullcontext, guarded_recheck=lambda _: True)
    assert not isinstance(outcome, Kr380EntryOutcomeV2)
    assert outcome.schema == ADVISORY_SCHEMA
    assert outcome.intrabar_trade_continuity == "UNVERIFIED"
    assert outcome.state.value == direction + "_ADVISORY_CONFIRMED"
    assert outcome.broker_authority == "NONE"


@pytest.mark.parametrize("change", [
    "previous_equal", "open_equal", "wick_only", "gap", "missing_interval",
    "revised_candle", "wrong_contract", "stale_receipt", "stale_v2",
    "session_break", "cutoff", "risk_rejected",
])
def test_v1_signal_rejects_changed_or_incomplete_evidence_without_writes(
    tmp_path, change,
):
    read = _v1_fixture()
    evaluated_at = read.current.closed_at
    if change == "previous_equal":
        read = replace(read, previous=replace(read.previous, close=read.plan.entry))
    elif change == "open_equal":
        read = replace(read, current=replace(read.current, open=read.plan.entry))
    elif change == "wick_only":
        read = replace(read, current=replace(read.current, close=Decimal("99")))
    elif change == "gap":
        read = replace(read, current=replace(read.current, open=Decimal("101")))
    elif change == "missing_interval":
        read = replace(read, continuity=replace(read.continuity,
                                                 no_missing_interval=False))
    elif change == "revised_candle":
        read = replace(read, current=replace(read.current, revision=2))
    elif change == "wrong_contract":
        read = replace(read, current=replace(read.current,
                                              trading_symbol="OTHER"))
    elif change == "stale_receipt":
        read = replace(read, authority=replace(read.authority,
                                                receipt_sha256="b" * 64))
    elif change == "stale_v2":
        read = replace(read, authority=replace(read.authority,
                                                v2_sha256="b" * 64))
    elif change == "session_break":
        read = replace(read, current=replace(read.current,
                                              session_identity="OTHER"))
    elif change == "cutoff":
        evaluated_at = read.plan.entry_eligibility_boundary
    else:
        read = replace(read, risk=replace(read.risk, state=RiskState.REJECTED,
                                          reason="REJECTED"))
    store = LocalMcxV1AdvisoryStore(tmp_path / "v1-outcomes")
    with pytest.raises((McxKr380Rejected, ValueError)):
        issue_v1_isolated_signal(
            lambda: read, evaluated_at=evaluated_at,
            store=store, commit_guard=nullcontext,
            guarded_recheck=lambda _digest: True)
    assert not store.root.exists()


def test_v1_signal_recheck_and_conflicting_replay_fail_closed(tmp_path):
    read = _v1_fixture()
    store = LocalMcxV1AdvisoryStore(tmp_path / "v1-outcomes")
    changed = replace(read, authority=replace(read.authority,
                                              v2_sha256="b" * 64))
    sequence = iter((read, changed))
    with pytest.raises(McxKr380Rejected, match="READ_SET_CHANGED"):
        issue_v1_isolated_signal(
            lambda: next(sequence), evaluated_at=read.current.closed_at,
            store=store, commit_guard=nullcontext,
            guarded_recheck=lambda _: True)
    with pytest.raises(McxKr380Rejected, match="COMMIT_FENCE_CHANGED"):
        issue_v1_isolated_signal(
            lambda: read, evaluated_at=read.current.closed_at,
            store=store, commit_guard=nullcontext,
            guarded_recheck=lambda _: False)
    assert not store.root.exists()
    first = issue_v1_isolated_signal(
        lambda: read, evaluated_at=read.current.closed_at,
        store=store, commit_guard=nullcontext,
        guarded_recheck=lambda _: True)
    revised = replace(read, current=replace(read.current,
                                             source_sha256="b" * 64),
                      continuity=replace(read.continuity,
                                         current_sha256="b" * 64))
    with pytest.raises(McxKr380Rejected, match="REPLAY_CONFLICT"):
        issue_v1_isolated_signal(
            lambda: revised, evaluated_at=read.current.closed_at,
            store=store, commit_guard=nullcontext,
            guarded_recheck=lambda _: True)
    assert store.load_for_plan(read.plan.trade_plan_id) == first


@pytest.mark.parametrize("family", list(McxFamily))
@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_five_family_confirmed_close_cross_is_isolated_and_idempotent(tmp_path, family, direction):
    read = _fixture(family, direction)
    store = LocalKr380V2Store(tmp_path / "outcomes")
    from kronos.swing.v1.mcx_kr380_issuer import _digest
    kwargs = dict(evaluated_at=read.current.closed_at+timedelta(minutes=1),
                  store=store, commit_guard=nullcontext,
                  guarded_recheck=lambda digest: digest == _digest(read))
    first = issue_isolated_mcx_kr380(lambda: read, **kwargs)
    assert first.state.value == direction + "_ENTRY_TRIGGERED"
    assert store.load_for_plan(read.plan_identity) == first
    before = tuple((p.name, p.read_bytes()) for p in (tmp_path/"outcomes").rglob("*") if p.is_file())
    assert issue_isolated_mcx_kr380(lambda: read, **kwargs) == first
    assert issue_isolated_mcx_kr380(
        lambda: read, **{**kwargs, "evaluated_at": read.current.closed_at+timedelta(minutes=2)},
    ) == first
    assert tuple((p.name, p.read_bytes()) for p in (tmp_path/"outcomes").rglob("*") if p.is_file()) == before


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_completed_close_equal_to_entry_is_a_signal(tmp_path, direction):
    read = _fixture(direction=direction)
    read = replace(read, current=replace(read.current, close=read.entry))
    outcome = issue_isolated_mcx_kr380(
        lambda: read, evaluated_at=read.current.closed_at+timedelta(minutes=1),
        store=LocalKr380V2Store(tmp_path/"outcomes"),
        commit_guard=nullcontext, guarded_recheck=lambda _: True,
    )
    assert outcome.state.value == direction + "_ENTRY_TRIGGERED"


@pytest.mark.parametrize("change", [
    "equality_previous", "equality_open", "wick_only", "opening_gap",
    "missing_interval", "session_break", "missing_gap_proof", "revised_candle",
    "incomplete_current", "wrong_contract", "stale_run", "stale_receipt", "stale_v2", "stale_master",
    "stale_specification", "missing_authority", "bad_notional",
    "bad_tick_value", "bad_stop_risk", "cutoff", "cutoff_proof", "risk_policy",
    "energy_supporting",
])
def test_invalid_or_changed_inputs_never_admit(tmp_path, change):
    read = _fixture(McxFamily.CRUDEOIL)
    if change == "equality_previous":
        read = replace(read, previous=replace(read.previous, close=read.entry))
    elif change == "equality_open":
        read = replace(read, current=replace(read.current, open=read.entry))
    elif change == "wick_only":
        read = replace(read, current=replace(read.current, close=Decimal("99")))
    elif change == "opening_gap":
        read = replace(read, continuity=replace(read.continuity, no_entry_spanning_gap=False))
    elif change == "missing_interval":
        read = replace(read, continuity=replace(read.continuity, no_missing_interval=False))
    elif change == "session_break":
        read = replace(read, continuity=replace(read.continuity, intervals_consecutive=False))
    elif change == "missing_gap_proof":
        read = replace(read, continuity=None)
    elif change == "revised_candle":
        read = replace(read, current=replace(read.current, revision=2))
    elif change == "wrong_contract":
        read = replace(read, current=replace(read.current, trading_symbol="OTHER"))
    elif change == "incomplete_current":
        read = replace(read, current=replace(read.current, confirmed_complete=False))
    elif change == "stale_run":
        read = replace(read, current_authority=replace(
            read.current_authority, run_identity="SUCCESSOR-RUN"))
    elif change == "stale_receipt":
        read = replace(read, proof=replace(read.proof, review_receipt_sha256="b"*64))
    elif change == "stale_v2":
        read = replace(read, proof=replace(read.proof, v2_sha256="b"*64))
    elif change == "stale_master":
        read = replace(read, proof=replace(read.proof, master_token=0))
    elif change == "stale_specification":
        read = replace(read, proof=replace(read.proof, specification_sha256=""))
    elif change == "missing_authority":
        read = replace(read, proof=replace(read.proof, missing_authority=("MCX_NUMERIC_RISK_POLICY_UNAPPROVED",)))
    elif change == "bad_notional":
        read = replace(read, proof=replace(read.proof, gross_notional=Decimal("1")))
    elif change == "bad_tick_value":
        read = replace(read, proof=replace(read.proof, rupees_per_tick=Decimal("1")))
    elif change == "bad_stop_risk":
        read = replace(read, proof=replace(read.proof, gross_stop_risk=Decimal("1")))
    elif change == "cutoff":
        read = replace(read, policy=replace(read.policy, entry_cutoff=read.current.closed_at))
    elif change == "cutoff_proof":
        read = replace(read, policy=replace(read.policy, broker_cutoff_sha256="b"*64))
    elif change == "risk_policy":
        read = replace(read, policy=replace(read.policy, maximum_gross_stop_risk_rupees=Decimal("1")))
    else:
        # Supporting reference states are absent from the execution read set.
        assert not hasattr(read, "comex") and not hasattr(read, "nymex")
        return
    store = LocalKr380V2Store(tmp_path / "outcomes")
    with pytest.raises((McxKr380Rejected, ValueError)):
        issue_isolated_mcx_kr380(
            lambda: read, evaluated_at=read.current.closed_at+timedelta(minutes=1),
            store=store, commit_guard=nullcontext, guarded_recheck=lambda _: True,
        )
    assert not (tmp_path/"outcomes").exists()


def test_readset_change_commit_fence_and_replay_conflict(tmp_path):
    read = _fixture()
    store = LocalKr380V2Store(tmp_path/"outcomes")
    at = read.current.closed_at+timedelta(minutes=1)
    changed = replace(
        read, proof=replace(read.proof, selection_sha256="b"*64),
        current_authority=replace(read.current_authority, selection_sha256="b"*64),
    )
    calls = iter((read, changed))
    with pytest.raises(McxKr380Rejected, match="READ_SET_CHANGED"):
        issue_isolated_mcx_kr380(lambda: next(calls), evaluated_at=at,
                                 store=store, commit_guard=nullcontext,
                                 guarded_recheck=lambda _: True)
    with pytest.raises(McxKr380Rejected, match="COMMIT_FENCE_CHANGED"):
        issue_isolated_mcx_kr380(lambda: read, evaluated_at=at,
                                 store=store, commit_guard=nullcontext,
                                 guarded_recheck=lambda _: False)
    assert not store.root.exists()
    issue_isolated_mcx_kr380(lambda: read, evaluated_at=at,
                             store=store, commit_guard=nullcontext,
                             guarded_recheck=lambda _: True)
    with pytest.raises(McxKr380Rejected, match="REPLAY_CONFLICT"):
        issue_isolated_mcx_kr380(lambda: changed, evaluated_at=at,
                                 store=store, commit_guard=nullcontext,
                                 guarded_recheck=lambda _: True)
