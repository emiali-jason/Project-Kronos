from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_wo14 import IntradayWo14Application
from kronos.application.intraday_wo15 import IntradayWo15Application
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo13 import Wo13GeometryAvailability
from kronos.intraday.wo13_pullback import construct_wo13_pullback_geometry
from kronos.intraday.wo14 import (
    Wo14ObservationState,
    create_wo14_observation_request,
)
from kronos.intraday.wo14_persistence import Wo14Store
from kronos.intraday.wo15 import (
    Wo15ProgressionSemantics,
    Wo15TimingState,
    create_wo15_wo13_handoff,
)
from kronos.intraday.wo15_persistence import (
    Wo15Store,
    create_wo15_operation_request,
)
from kronos.intraday.wo16 import (
    WO16_ADMISSION_IDENTITY,
    WO16_AUTHORITY,
    WO16_CONTRACT_VERSION,
    WO16_DECISION_IDENTITY,
    WO16_POLICY_CHECKSUM,
    WO16_POLICY_IDENTITY,
    WO16_POLICY_VERSION,
    WO16_SNAPSHOT_IDENTITY,
    Wo16AdmissionReason,
    Wo16ContractError,
    Wo16DecisionSource,
    Wo16LifecycleAdmissionDisposition,
    Wo16PolicyBinding,
    Wo16SponsorDecision,
    Wo16SuccessorTrigger,
    canonical_document_bytes,
    create_wo16_lifecycle_admission_record,
    create_wo16_sponsor_decision_record,
    create_wo16_sponsor_decision_snapshot,
    create_wo16_successor_lineage,
    disposition_for_decision,
)
from kronos.intraday.wo16_adapters import (
    bind_wo16_risk_observation,
    bind_wo16_session_fact,
    bind_wo16_timing_handoff,
    bind_wo16_trade_plan,
    bind_wo16_upstream,
)
from kronos.market.schedule import (
    InMemoryMarketScheduleSource,
    MarketDaySchedule,
    MarketSessionService,
    MarketWindow,
    TradingDayStatus,
)

from .test_wo13_application import _execute
from .test_wo13_targets import _pullback
from .test_wo13_pullback import (
    _evidence as _pullback_evidence,
    _fact as _pullback_fact,
    _facts as _pullback_facts,
    _mcx_handoff,
)
from .test_wo15_contracts import _session
from .test_wo15_timing import _candle, _progression


def _chain(
    tmp_path: Path,
    *,
    mcx: bool = False,
    direction: SemanticDirection = SemanticDirection.LONG,
):
    if mcx:
        mcx_handoff = _mcx_handoff(tmp_path)
        facts = tuple(
            _pullback_fact(
                mcx_handoff,
                str(item.price),
                item.structural_role,
                source=item.source_evidence_identity,
                session="MCX-SESSION-2026-08-31",
            )
            for item in _pullback_facts(mcx_handoff)
        )
        geometry = construct_wo13_pullback_geometry(
            _pullback_evidence(
                mcx_handoff,
                qualification=(facts[0],),
                pullback=(facts[1],),
                impulse=(facts[2],),
                session="MCX-SESSION-2026-08-31",
            )
        )
    else:
        geometry = _pullback(tmp_path, direction)
    wo13_store, _, wo13_execution = _execute(tmp_path, geometry)
    plan = wo13_execution.trade_plan
    pointer13 = wo13_execution.pointer
    handoff13 = geometry.evidence.handoff
    assert plan.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE

    request14 = create_wo14_observation_request(
        plan=plan,
        sponsor_operation_identity="SPONSOR-WO16-SLICE1-RISK-FIXTURE",
        requested_at=plan.analysis_boundary,
        evaluation_boundary=plan.analysis_boundary,
        provenance=("ADR-0023", "WO-16-SLICE-1-TEST"),
    )
    store14 = Wo14Store((tmp_path / "wo14").resolve())
    execution14 = IntradayWo14Application(
        wo13_store=wo13_store, store=store14
    ).execute(request14)

    admission15 = create_wo15_wo13_handoff(
        current_pointer=pointer13,
        trade_plan=plan,
        source_handoff=handoff13,
    )
    session15 = _session(admission15)
    source, evidence = _candle(
        admission15,
        session15,
        minute=5,
        close=("101" if direction is SemanticDirection.LONG else "99"),
    )
    progression = _progression(
        admission15, evidence, Wo15ProgressionSemantics.ALIGNED
    )
    request15 = create_wo15_operation_request(
        admission=admission15,
        session=session15,
        source_candle=source,
        evidence=evidence,
        progression=progression,
        observed_at=evidence.candle_end + timedelta(seconds=1),
        provenance=("ADR-0025", "WO-16-SLICE-1-TEST"),
    )
    store15 = Wo15Store((tmp_path / "wo15").resolve())
    execution15 = IntradayWo15Application(
        wo13_store=wo13_store, store=store15
    ).execute(request15)
    assert execution15.timing_handoff is not None
    assert execution15.pointer.timing_state is Wo15TimingState.TIMING_QUALIFIED

    schedule = MarketDaySchedule(
        exchange=session15.exchange,
        trading_date=session15.trading_date,
        session_id=session15.session_identity,
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=tuple(MarketWindow(*window) for window in session15.windows),
        source_identity=session15.calendar_identity,
        source_version=session15.calendar_version,
    )
    observed_at = session15.session_opens_at + timedelta(minutes=1)
    fact = MarketSessionService(
        InMemoryMarketScheduleSource((schedule,))
    ).facts(
        exchange=session15.exchange,
        trading_date=session15.trading_date,
        observed_at=observed_at,
    )

    trade = bind_wo16_trade_plan(
        current_pointer=pointer13,
        trade_plan=plan,
        source_handoff=handoff13,
    )
    risk = bind_wo16_risk_observation(
        current_pointer=execution14.pointer,
        observation=execution14.observation,
        trade_plan=trade,
    )
    timing = bind_wo16_timing_handoff(
        current_pointer=execution15.pointer,
        handoff=execution15.timing_handoff,
        trade_plan=trade,
        risk_observation=risk,
    )
    session = bind_wo16_session_fact(
        wo15_session=session15,
        fact=fact,
        timing_handoff=timing,
    )
    lineage = bind_wo16_upstream(
        trade_plan=trade,
        risk_observation=risk,
        timing_handoff=timing,
        session=session,
    )
    snapshot = create_wo16_sponsor_decision_snapshot(
        upstream_lineage=lineage,
        snapshot_timestamp=observed_at + timedelta(seconds=1),
    )
    return {
        "plan": plan,
        "pointer13": pointer13,
        "handoff13": handoff13,
        "observation14": execution14.observation,
        "pointer14": execution14.pointer,
        "session15": session15,
        "handoff15": execution15.timing_handoff,
        "pointer15": execution15.pointer,
        "fact": fact,
        "trade": trade,
        "risk": risk,
        "timing": timing,
        "session": session,
        "lineage": lineage,
        "snapshot": snapshot,
        "observed_at": observed_at,
    }


def _decision(chain, choice=Wo16SponsorDecision.PAPER):  # type: ignore[no-untyped-def]
    return create_wo16_sponsor_decision_record(
        snapshot=chain["snapshot"],
        request_identity="INTRADAY-WO16-REQUEST-TEST",
        request_integrity="INTEGRITY-INTRADAY-WO16-REQUEST-TEST",
        choice=choice,
        decision_timestamp=chain["observed_at"] + timedelta(seconds=2),
    )


def test_policy_identity_version_checksum_and_negative_authority_are_exact() -> None:
    policy = Wo16PolicyBinding()
    assert (
        policy.policy_identity,
        policy.policy_version,
        policy.policy_checksum,
        policy.authority,
    ) == (
        WO16_POLICY_IDENTITY,
        WO16_POLICY_VERSION,
        WO16_POLICY_CHECKSUM,
        WO16_AUTHORITY,
    )
    assert not any(
        value
        for name, value in asdict(policy).items()
        if name.endswith("_authority")
    )


def test_governed_policy_json_checksum_matches_constant() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "docs/architecture/products/intraday"
        / "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-POLICY-V1.json"
    )
    assert sha256(path.read_bytes()).hexdigest() == WO16_POLICY_CHECKSUM


def test_contracts_are_immutable_and_canonical_bytes_are_deterministic(tmp_path) -> None:
    chain = _chain(tmp_path)
    assert canonical_document_bytes(chain["snapshot"]) == canonical_document_bytes(
        chain["snapshot"]
    )
    with pytest.raises(FrozenInstanceError):
        chain["snapshot"].snapshot_identity = "CHANGED"


@pytest.mark.parametrize(
    ("enum_type", "value"),
    (
        (Wo16SponsorDecision, "MAYBE"),
        (Wo16DecisionSource, "REMOTE_USER"),
        (Wo16LifecycleAdmissionDisposition, "POSITION_OPEN"),
        (Wo16AdmissionReason, "SWING_REASON"),
        (Wo16SuccessorTrigger, "LATEST_FILE"),
    ),
)
def test_enums_reject_unknown_values(enum_type, value) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        enum_type(value)


def test_same_facts_same_identity_and_changed_decision_changes_identity(tmp_path) -> None:
    chain = _chain(tmp_path)
    paper_a = _decision(chain)
    paper_b = _decision(chain)
    live = _decision(chain, Wo16SponsorDecision.LIVE)
    assert paper_a == paper_b
    assert paper_a.decision_identity == paper_b.decision_identity
    assert paper_a.decision_identity != live.decision_identity


def test_changed_integrity_and_naive_timestamp_fail_closed(tmp_path) -> None:
    chain = _chain(tmp_path)
    with pytest.raises(Wo16ContractError, match="WO16_SPONSOR_DECISION_SNAPSHOT_INVALID"):
        replace(chain["snapshot"], snapshot_integrity="CORRUPT")
    with pytest.raises(Wo16ContractError, match="WO16_TIMESTAMP_TIMEZONE_REQUIRED"):
        create_wo16_sponsor_decision_record(
            snapshot=chain["snapshot"],
            request_identity="REQUEST",
            request_integrity="INTEGRITY",
            choice=Wo16SponsorDecision.PAPER,
            decision_timestamp=datetime(2026, 9, 2, 10, 0),
        )


def test_float_and_non_finite_decimal_are_rejected() -> None:
    with pytest.raises(Wo16ContractError, match="WO16_FLOAT_PROHIBITED"):
        canonical_document_bytes({"price": 1.25})
    with pytest.raises(Wo16ContractError, match="WO16_DECIMAL_INVALID"):
        canonical_document_bytes({"price": Decimal("NaN")})


@pytest.mark.parametrize(
    ("choice", "disposition", "reason"),
    (
        (
            Wo16SponsorDecision.PAPER,
            Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE,
            Wo16AdmissionReason.PAPER_INTENT_RECORDED,
        ),
        (
            Wo16SponsorDecision.LIVE,
            Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE,
            Wo16AdmissionReason.LIVE_INTENT_RECORDED,
        ),
        (
            Wo16SponsorDecision.IGNORE,
            Wo16LifecycleAdmissionDisposition.NOT_APPLICABLE_IGNORE,
            Wo16AdmissionReason.EXACT_LINEAGE_IGNORED,
        ),
    ),
)
def test_frozen_decision_to_disposition_mapping(choice, disposition, reason) -> None:  # type: ignore[no-untyped-def]
    assert disposition_for_decision(choice) == (disposition, reason)


@pytest.mark.parametrize("choice", tuple(Wo16SponsorDecision))
def test_admission_is_factual_only_and_contains_no_position_truth(tmp_path, choice) -> None:  # type: ignore[no-untyped-def]
    chain = _chain(tmp_path)
    decision = _decision(chain, choice)
    admission = create_wo16_lifecycle_admission_record(
        decision=decision,
        recorded_at=chain["observed_at"] + timedelta(seconds=3),
    )
    assert admission.schema_identity == WO16_ADMISSION_IDENTITY
    assert admission.position_consequence == "NONE"
    assert not any(
        getattr(admission, name)
        for name in (
            "position_authority",
            "fill_authority",
            "quantity_authority",
            "monitoring_authority",
            "execution_authority",
            "broker_authority",
        )
    )
    forbidden = {
        "person_identity",
        "sponsor_name",
        "email",
        "free_text_rationale",
        "broker_account",
        "order_identity",
        "fill_price",
        "fill_timestamp",
        "quantity",
        "fees",
        "pnl",
        "realised_r",
    }
    assert forbidden.isdisjoint(asdict(decision))
    assert forbidden.isdisjoint(asdict(admission))


def test_contract_identities_are_exact(tmp_path) -> None:
    chain = _chain(tmp_path)
    decision = _decision(chain)
    admission = create_wo16_lifecycle_admission_record(
        decision=decision,
        recorded_at=chain["observed_at"] + timedelta(seconds=3),
    )
    assert chain["snapshot"].schema_identity == WO16_SNAPSHOT_IDENTITY
    assert decision.schema_identity == WO16_DECISION_IDENTITY
    assert admission.schema_identity == WO16_ADMISSION_IDENTITY
    assert {chain["snapshot"].schema_version, decision.schema_version, admission.schema_version} == {
        WO16_CONTRACT_VERSION
    }


def test_successor_lineage_preserves_predecessor_and_ignore_is_exact_lineage(tmp_path) -> None:
    chain = _chain(tmp_path)
    ignored = _decision(chain, Wo16SponsorDecision.IGNORE)
    later = create_wo16_sponsor_decision_snapshot(
        upstream_lineage=chain["lineage"],
        snapshot_timestamp=chain["observed_at"] + timedelta(seconds=10),
    )
    successor = create_wo16_successor_lineage(
        predecessor=ignored,
        successor_snapshot=later,
        trigger=Wo16SuccessorTrigger.MARKET_SESSION,
    )
    assert successor.predecessor_decision_identity == ignored.decision_identity
    assert successor.successor_snapshot_identity == later.snapshot_identity
    assert successor.prior_record_mutation == "PROHIBITED"
    assert ignored.choice is Wo16SponsorDecision.IGNORE


def test_missing_and_extra_constructor_fields_are_rejected(tmp_path) -> None:
    chain = _chain(tmp_path)
    values = asdict(_decision(chain))
    values.pop("request_identity")
    with pytest.raises(TypeError):
        type(_decision(chain))(**values)
    values = asdict(_decision(chain))
    values["convenient_default"] = True
    with pytest.raises(TypeError):
        type(_decision(chain))(**values)


def test_no_swing_step32_or_actual_position_fields_exist(tmp_path) -> None:
    names = set(asdict(_decision(_chain(tmp_path))))
    assert not any("swing" in name.lower() or "step32" in name.lower() for name in names)
    assert {"actual_fill_price", "monetary_pnl", "realised_r"}.isdisjoint(names)


def test_timezone_aware_ist_timestamp_is_preserved_without_conversion(tmp_path) -> None:
    chain = _chain(tmp_path)
    timestamp = datetime(2026, 9, 2, 13, 7, 3, tzinfo=ZoneInfo("Asia/Kolkata"))
    record = create_wo16_sponsor_decision_record(
        snapshot=chain["snapshot"],
        request_identity="REQUEST-TIMEZONE",
        request_integrity="INTEGRITY-TIMEZONE",
        choice=Wo16SponsorDecision.PAPER,
        decision_timestamp=timestamp,
    )
    assert record.decision_timestamp is timestamp
    assert b"2026-09-02T13:07:03+05:30" in canonical_document_bytes(record)
