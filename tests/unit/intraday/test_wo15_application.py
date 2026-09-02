from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from kronos.application.intraday_wo15 import (
    IntradayWo15Application,
    IntradayWo15RestorationService,
    Wo15ApplicationError,
)
from kronos.intraday.wo13_persistence import Wo13Store
from kronos.intraday.wo15 import (
    Wo15ExpiryCause,
    Wo15ProgressionSemantics,
    Wo15TimingState,
)
from kronos.intraday.wo15_persistence import (
    Wo15OperationOutcome,
    Wo15Store,
    Wo15SupersessionReason,
    create_wo15_operation_request,
)
from kronos.intraday.wo15_telemetry import bind_wo15_telemetry_candle
from kronos.intraday.wo15_timing import create_wo15_expiry_event

from .test_wo15_contracts import _mcx_wo13, _session, _wo13
from .test_wo15_timing import _candle, _progression


def _persist_wo13(root, values):  # type: ignore[no-untyped-def]
    handoff, request, plan, operation, pointer, admission = values
    store = Wo13Store(root.resolve())
    store.retain_handoff(handoff)
    store.retain_request(request)
    store.retain_trade_plan(plan)
    store.retain_operation(operation)
    store.publish_current(pointer)
    return store, admission


def _environment(
    tmp_path,
    *,
    minute: int = 5,
    close: str = "101",
    semantics: Wo15ProgressionSemantics = Wo15ProgressionSemantics.ALIGNED,
    mcx: bool = False,
):
    values = _mcx_wo13(tmp_path) if mcx else _wo13(tmp_path)
    wo13_store, admission = _persist_wo13(tmp_path / "wo13", values)
    session = _session(admission)
    source, evidence = _candle(
        admission, session, minute=minute, close=close
    )
    progression = _progression(admission, evidence, semantics)
    request = create_wo15_operation_request(
        admission=admission,
        session=session,
        source_candle=source,
        evidence=evidence,
        progression=progression,
        observed_at=evidence.candle_end + timedelta(seconds=1),
        provenance=("ADR-0025", "WO-15D-TEST"),
    )
    store = Wo15Store((tmp_path / "wo15").resolve())
    app = IntradayWo15Application(wo13_store=wo13_store, store=store)
    return wo13_store, store, app, request


def _next_request(
    request,
    *,
    minute: int,
    close: str,
    semantics: Wo15ProgressionSemantics,
    expiry_event=None,
):
    source, evidence = _candle(
        request.admission, request.session, minute=minute, close=close,
        high=str(max(101, int(float(close)) + 1)),
    )
    progression = _progression(request.admission, evidence, semantics)
    return create_wo15_operation_request(
        admission=request.admission,
        session=request.session,
        source_candle=source,
        evidence=evidence,
        progression=progression,
        observed_at=evidence.candle_end + timedelta(seconds=1),
        expiry_event=expiry_event,
        provenance=request.provenance,
    )


def test_qualified_operation_persists_restores_and_publishes_handoff(tmp_path) -> None:
    _, store, app, request = _environment(tmp_path)
    execution = app.execute(request)
    assert execution.timing_result.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert execution.timing_handoff is not None
    assert execution.operation.outcome is Wo15OperationOutcome.COMPLETED
    assert store.load_current() == execution.pointer
    assert (
        store.root / "current" / f"{execution.pointer.pointer_identity}.json"
    ).exists()
    assert store.restore_current().result == execution.timing_result  # type: ignore[union-attr]


def test_waiting_operation_publishes_no_downstream_handoff(tmp_path) -> None:
    _, _, app, request = _environment(tmp_path, close="100")
    execution = app.execute(request)
    assert execution.timing_result.current_state is Wo15TimingState.TIMING_WAITING
    assert execution.timing_handoff is None
    assert execution.pointer.timing_handoff_identity is None


def test_exact_request_replay_is_idempotent(tmp_path) -> None:
    _, store, app, request = _environment(tmp_path)
    first = app.execute(request)
    second = app.execute(request)
    assert second.replayed
    assert second.pointer == first.pointer
    assert len(tuple((store.root / "results").glob("*.json"))) == 1


def test_not_yet_run_loaded_and_corrupt_restoration_states(tmp_path) -> None:
    _, store, app, request = _environment(tmp_path)
    service = IntradayWo15RestorationService(store=store)
    assert service.restore().state == "NOT_YET_RUN"
    app.execute(request)
    assert service.restore().state == "LOADED"
    (store.root / "current" / "CURRENT-INTRADAY-WO15-V1.json").write_text(
        "{}", encoding="utf-8"
    )
    status = service.restore()
    assert status.state == "CORRUPT"
    assert status.failure_reason == "WO15_RESTORATION_FAILED"


def test_nonblocking_concurrency_rejection(tmp_path) -> None:
    _, _, app, request = _environment(tmp_path)
    assert app._lock.acquire(blocking=False)  # noqa: SLF001 - lock proof
    try:
        with pytest.raises(Wo15ApplicationError, match="WO15_OPERATION_BUSY"):
            app.execute(request)
    finally:
        app._lock.release()  # noqa: SLF001


def test_stale_wo13_plan_is_rejected_and_failure_is_separate(tmp_path) -> None:
    wo13_store, store, app, request = _environment(tmp_path)
    newer = _wo13(tmp_path, minute=35)
    for item, retain in (
        (newer[0], wo13_store.retain_handoff),
        (newer[1], wo13_store.retain_request),
        (newer[2], wo13_store.retain_trade_plan),
        (newer[3], wo13_store.retain_operation),
    ):
        retain(item)
    wo13_store.publish_current(newer[4])
    with pytest.raises(Wo15ApplicationError, match="WO15_SUPERSEDED_WO13_REJECTED"):
        app.execute(request)
    assert store.load_current() is None
    assert store.load_latest_failure() is not None


def test_failed_later_operation_preserves_prior_current_pointer(tmp_path) -> None:
    _, store, app, request = _environment(tmp_path)
    first = app.execute(request)
    foreign_source, foreign = _candle(
        request.admission, request.session, minute=10, close="102", high="103",
        instrument_identity="FOREIGN-INSTRUMENT",
    )
    foreign_progression = _progression(
        request.admission, foreign, Wo15ProgressionSemantics.ALIGNED
    )
    bad = create_wo15_operation_request(
        admission=request.admission,
        session=request.session,
        source_candle=foreign_source,
        evidence=foreign,
        progression=foreign_progression,
        observed_at=foreign.candle_end + timedelta(seconds=1),
    )
    with pytest.raises(Wo15ApplicationError, match="WO15_REQUEST_LINEAGE_MISMATCH"):
        app.execute(bad)
    assert store.load_current() == first.pointer
    assert store.load_latest_failure() is not None


def test_nse_instrument_mismatch_rejected(tmp_path) -> None:
    _, _, app, request = _environment(tmp_path)
    source, bad_evidence = _candle(
        request.admission, request.session, minute=10, close="101",
        instrument_identity="FOREIGN-INSTRUMENT",
    )
    progression = _progression(
        request.admission, bad_evidence, Wo15ProgressionSemantics.ALIGNED
    )
    bad = create_wo15_operation_request(
        admission=request.admission, session=request.session,
        source_candle=source, evidence=bad_evidence,
        progression=progression,
        observed_at=bad_evidence.candle_end + timedelta(seconds=1),
    )
    with pytest.raises(Wo15ApplicationError, match="WO15_REQUEST_LINEAGE_MISMATCH"):
        app.execute(bad)


@pytest.mark.parametrize("field", ("actual_contract_identity", "roll_lineage_identity"))
def test_mcx_contract_and_roll_mismatch_rejected(tmp_path, field) -> None:
    _, _, app, request = _environment(tmp_path, mcx=True)
    kwargs = {field: f"FOREIGN-{field}"}
    source, bad_evidence = _candle(
        request.admission, request.session, minute=10, close="101", **kwargs
    )
    progression = _progression(
        request.admission, bad_evidence, Wo15ProgressionSemantics.ALIGNED
    )
    bad = create_wo15_operation_request(
        admission=request.admission, session=request.session,
        source_candle=source, evidence=bad_evidence,
        progression=progression,
        observed_at=bad_evidence.candle_end + timedelta(seconds=1),
    )
    with pytest.raises(Wo15ApplicationError, match="WO15_REQUEST_LINEAGE_MISMATCH"):
        app.execute(bad)


def test_cross_session_evidence_rejected(tmp_path) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from kronos.intraday.wo15 import bind_wo15_session
    from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus

    _, _, app, request = _environment(tmp_path)
    day = request.session.trading_date
    zone = ZoneInfo("Asia/Kolkata")
    foreign_session = bind_wo15_session(MarketDaySchedule(
        exchange="NSE", trading_date=day, session_id="NSE-FOREIGN-SESSION",
        timezone="Asia/Kolkata", status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            datetime(day.year, day.month, day.day, 9, 15, tzinfo=zone),
            datetime(day.year, day.month, day.day, 15, 30, tzinfo=zone),
        ),),
        source_identity="KRONOS-NSE-CALENDAR-V1", source_version="1.0.0",
    ))
    bad = create_wo15_operation_request(
        admission=request.admission, session=foreign_session,
        source_candle=request.source_candle, evidence=request.evidence,
        progression=request.progression, observed_at=request.observed_at,
    )
    with pytest.raises(Wo15ApplicationError, match="WO15_REQUEST_LINEAGE_MISMATCH"):
        app.execute(bad)


def test_cross_cycle_progression_evidence_rejected(tmp_path) -> None:
    _, _, app, request = _environment(tmp_path)
    source, evidence = _candle(
        request.admission, request.session, minute=10, close="102", high="103"
    )
    bad = create_wo15_operation_request(
        admission=request.admission,
        session=request.session,
        source_candle=source,
        evidence=evidence,
        progression=request.progression,
        observed_at=evidence.candle_end + timedelta(seconds=1),
    )
    with pytest.raises(Wo15ApplicationError, match="WO15_REQUEST_LINEAGE_MISMATCH"):
        app.execute(bad)


def test_failed_cycle_reset_creates_explicit_successor_lineage(tmp_path) -> None:
    _, _, app, request = _environment(
        tmp_path, close="100", semantics=Wo15ProgressionSemantics.CONTRADICTORY
    )
    failed = app.execute(request)
    assert failed.timing_result.current_state is Wo15TimingState.TIMING_FAILED
    successor_request = _next_request(
        request, minute=10, close="101",
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    successor = app.execute(successor_request)
    assert successor.reset_assessment is not None
    assert successor.reset_assessment.eligible
    assert successor.supersession.reason is (  # type: ignore[union-attr]
        Wo15SupersessionReason.RESET_SUCCESSOR_CYCLE
    )
    assert successor.timing_result.timing_cycle_id != failed.timing_result.timing_cycle_id


def test_qualified_then_expired_handoff_preserves_predecessor(tmp_path) -> None:
    _, _, app, request = _environment(tmp_path)
    qualified = app.execute(request)
    later_source, later_evidence = _candle(
        request.admission, request.session, minute=10, close="102", high="103"
    )
    event = create_wo15_expiry_event(
        cause=Wo15ExpiryCause.WO13_PLAN_SUPERSEDED,
        event_boundary=later_evidence.candle_end,
        source_identity="WO13-SUPERSESSION-EVENT",
        source_integrity="INTEGRITY-WO13-SUPERSESSION-EVENT",
        admission=request.admission,
        session=request.session,
    )
    progression = _progression(
        request.admission, later_evidence, Wo15ProgressionSemantics.ALIGNED
    )
    expired_request = create_wo15_operation_request(
        admission=request.admission, session=request.session,
        source_candle=later_source, evidence=later_evidence,
        progression=progression,
        observed_at=later_evidence.candle_end + timedelta(seconds=1),
        expiry_event=event,
    )
    expired = app.execute(expired_request)
    assert expired.timing_result.current_state is Wo15TimingState.TIMING_EXPIRED
    assert expired.timing_handoff.predecessor_handoff_identity == (  # type: ignore[union-attr]
        qualified.timing_handoff.handoff_identity  # type: ignore[union-attr]
    )


def test_telemetry_persists_but_cannot_change_timing_state(tmp_path) -> None:
    wo13_store, store, _, request = _environment(tmp_path)
    bound = []
    for index, minute in enumerate(range(5, 75, 5)):
        source, evidence = _candle(
            request.admission, request.session, minute=minute,
            close="100", high="102", low="98",
        )
        bound.append(bind_wo15_telemetry_candle(
            source=source, evidence=evidence, admission=request.admission,
            session=request.session, sequence_index=index,
        ))
    final_source, final_evidence = _candle(
        request.admission, request.session, minute=75,
        close="101", high="102", low="98",
    )
    final_progression = _progression(
        request.admission, final_evidence, Wo15ProgressionSemantics.ALIGNED
    )
    measurement = bind_wo15_telemetry_candle(
        source=final_source, evidence=final_evidence,
        admission=request.admission, session=request.session, sequence_index=14,
    )
    with_telemetry = create_wo15_operation_request(
        admission=request.admission, session=request.session,
        source_candle=final_source, evidence=final_evidence,
        progression=final_progression,
        observed_at=final_evidence.candle_end + timedelta(seconds=1),
        telemetry_measurement=measurement,
        telemetry_atr_history=(*bound, measurement),
        telemetry_cycle_history=(measurement,),
    )
    result = IntradayWo15Application(
        wo13_store=wo13_store, store=store
    ).execute(with_telemetry)
    assert result.telemetry is not None
    assert result.telemetry.timing_state_observed is result.timing_result.current_state
    assert not result.telemetry.timing_decision_authority


def test_missing_optional_telemetry_is_unavailable_without_failure(tmp_path) -> None:
    _, _, app, request = _environment(tmp_path)
    result = app.execute(request)
    assert result.telemetry is None
    assert result.operation.outcome is Wo15OperationOutcome.COMPLETED


@pytest.mark.parametrize("risk_state", ("RISK_OBSERVED", "RISK_ALERT", "RISK_UNAVAILABLE"))
def test_wo14_state_never_vetoes_identical_timing(tmp_path, risk_state) -> None:
    _, _, app, request = _environment(tmp_path)
    contextual = replace(
        create_wo15_operation_request(
            admission=request.admission, session=request.session,
            source_candle=request.source_candle, evidence=request.evidence,
            progression=request.progression, observed_at=request.observed_at,
            wo14_reference_state=risk_state,
        ),
    )
    result = app.execute(contextual)
    assert result.timing_result.current_state is Wo15TimingState.TIMING_QUALIFIED


def test_policy_binding_and_negative_authorities_preserved(tmp_path) -> None:
    _, _, app, request = _environment(tmp_path)
    result = app.execute(request)
    assert result.pointer.policy == request.admission.policy
    assert result.timing_handoff.timing_evidence_authority  # type: ignore[union-attr]
    assert result.timing_handoff.sponsor_decision_authority == "NONE"  # type: ignore[union-attr]
    assert result.timing_handoff.broker_authority == "NONE"  # type: ignore[union-attr]


def test_modules_do_not_import_provider_browser_or_runtime() -> None:
    from pathlib import Path

    root = Path(__file__).parents[3]
    text = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in (
            "src/kronos/intraday/wo15_persistence.py",
            "src/kronos/application/intraday_wo15.py",
        )
    )
    assert "kronos.provider" not in text
    assert "kronos.browser" not in text
    assert "kronos.intraday.runtime" not in text
