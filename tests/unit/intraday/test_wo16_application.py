from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from kronos.application.intraday_wo16 import (
    IntradayWo16Application,
    Wo16ApplicationError,
    Wo16ApplicationOutcome,
    Wo16BusyOutcome,
    create_wo16_operation_request,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo15 import Wo15TimingState
from kronos.intraday.wo16 import (
    Wo16AdmissionReason,
    Wo16LifecycleAdmissionDisposition,
    Wo16SponsorDecision,
)

from .test_wo16_adapters import _fact
from .test_wo16_contracts import _chain


def _request(chain, choice=Wo16SponsorDecision.PAPER, **changes):  # type: ignore[no-untyped-def]
    observed_at = chain["observed_at"]
    values = {
        "current_wo13_pointer": chain["pointer13"],
        "wo13_trade_plan": chain["plan"],
        "wo13_source_handoff": chain["handoff13"],
        "current_wo14_pointer": chain["pointer14"],
        "wo14_observation": chain["observation14"],
        "current_wo15_pointer": chain["pointer15"],
        "wo15_timing_handoff": chain["handoff15"],
        "wo15_session": chain["session15"],
        "domain_008_session_fact": chain["fact"],
        "choice": choice,
        "snapshot_timestamp": observed_at + timedelta(seconds=1),
        "decision_timestamp": observed_at + timedelta(seconds=2),
        "admission_recorded_at": observed_at + timedelta(seconds=3),
        "provenance": ("ADR-0026", "WO-16-SLICE-2-TEST"),
    }
    values.update(changes)
    return create_wo16_operation_request(**values)


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
def test_exact_decision_and_admission_disposition(
    tmp_path, choice, disposition, reason
) -> None:  # type: ignore[no-untyped-def]
    chain = _chain(tmp_path)
    result = IntradayWo16Application().execute(_request(chain, choice))
    assert result.outcome is Wo16ApplicationOutcome.COMPLETED
    assert result.decision.choice is choice
    assert result.admission.disposition is disposition
    assert result.admission.reason is reason
    assert result.admission.position_consequence == "NONE"
    assert result.upstream_lineage.trade_plan.trade_plan_identity == (
        chain["plan"].trade_plan_identity
    )


def test_exact_replay_returns_retained_records_idempotently(tmp_path) -> None:
    chain = _chain(tmp_path)
    application = IntradayWo16Application()
    request = _request(chain)
    first = application.execute(request)
    second = application.execute(request, retained=first)
    assert second.outcome is Wo16ApplicationOutcome.RETAINED_IDEMPOTENT
    assert second.replayed
    assert second.decision == first.decision
    assert second.admission == first.admission
    assert second.snapshot == first.snapshot


def test_different_choice_for_final_exact_lineage_is_rejected(tmp_path) -> None:
    chain = _chain(tmp_path)
    application = IntradayWo16Application()
    first = application.execute(_request(chain, Wo16SponsorDecision.PAPER))
    with pytest.raises(Wo16ApplicationError, match="WO16_DECISION_ALREADY_FINAL"):
        application.execute(
            _request(chain, Wo16SponsorDecision.LIVE), retained=first
        )


def test_same_request_identity_with_conflicting_canonical_bytes_is_rejected(
    tmp_path,
) -> None:
    chain = _chain(tmp_path)
    application = IntradayWo16Application()
    request = _request(chain)
    first = application.execute(request)
    corrupt = _copy_slots(request)
    object.__setattr__(corrupt, "choice", Wo16SponsorDecision.LIVE)
    with pytest.raises(Wo16ApplicationError, match="WO16_REQUEST_INVALID"):
        application.execute(corrupt, retained=first)


def test_corrupt_retained_decision_bytes_fail_closed(tmp_path) -> None:
    chain = _chain(tmp_path)
    application = IntradayWo16Application()
    request = _request(chain)
    first = application.execute(request)
    decision = _copy_slots(first.decision)
    object.__setattr__(decision, "choice", Wo16SponsorDecision.LIVE)
    retained = _copy_slots(first)
    object.__setattr__(retained, "decision", decision)
    with pytest.raises(Wo16ApplicationError, match="WO16_RETAINED_STATE_INVALID"):
        application.execute(request, retained=retained)


def test_stale_wo13_plan_is_rejected(tmp_path) -> None:
    first = _chain(tmp_path / "first")
    second = _chain(tmp_path / "second", direction=SemanticDirection.SHORT)
    request = _request(
        first,
        current_wo13_pointer=second["pointer13"],
    )
    with pytest.raises(Wo16ApplicationError, match="WO13_NOT_CURRENT"):
        IntradayWo16Application().execute(request)


def test_mismatched_wo14_lineage_is_rejected(tmp_path) -> None:
    first = _chain(tmp_path / "first")
    second = _chain(tmp_path / "second", direction=SemanticDirection.SHORT)
    request = _request(
        first,
        current_wo14_pointer=second["pointer14"],
        wo14_observation=second["observation14"],
    )
    with pytest.raises(
        Wo16ApplicationError,
        match="WO14_(NOT_CURRENT|PLAN_MISMATCH)",
    ):
        IntradayWo16Application().execute(request)


def test_wo14_unavailable_remains_advisory(tmp_path) -> None:
    chain = _chain(tmp_path, mcx=True)
    assert chain["observation14"].state.value == "RISK_UNAVAILABLE"
    result = IntradayWo16Application().execute(_request(chain))
    assert result.decision.choice is Wo16SponsorDecision.PAPER
    assert result.admission.disposition is (
        Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE
    )
    assert not result.upstream_lineage.risk_observation.trade_veto_authority


def test_wo14_warning_state_is_advisory_at_application_boundary(tmp_path) -> None:
    chain = _chain(tmp_path)
    observation, pointer = _wo14_state(
        chain, type(chain["observation14"].state).RISK_ALERT
    )
    request = _request(
        chain,
        current_wo14_pointer=pointer,
        wo14_observation=observation,
    )
    result = IntradayWo16Application().execute(request)
    assert result.upstream_lineage.risk_observation.state.value == "RISK_ALERT"
    assert not result.upstream_lineage.risk_observation.trade_veto_authority
    assert result.admission.disposition is (
        Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE
    )


@pytest.mark.parametrize(
    "state",
    (
        Wo15TimingState.TIMING_NOT_EVALUATED,
        Wo15TimingState.TIMING_WAITING,
        Wo15TimingState.TIMING_FAILED,
        Wo15TimingState.TIMING_EXPIRED,
        Wo15TimingState.TIMING_UNAVAILABLE,
    ),
)
def test_every_nonqualified_timing_state_is_rejected(tmp_path, state) -> None:  # type: ignore[no-untyped-def]
    chain = _chain(tmp_path)
    request = _request(chain, current_wo15_pointer=_wo15_state(chain, state))
    with pytest.raises(
        Wo16ApplicationError, match="WO15_TIMING_NOT_QUALIFIED"
    ):
        IntradayWo16Application().execute(request)


def test_stale_or_noncurrent_wo15_handoff_is_rejected(tmp_path) -> None:
    first = _chain(tmp_path / "first")
    second = _chain(tmp_path / "second", direction=SemanticDirection.SHORT)
    request = _request(
        first,
        current_wo15_pointer=second["pointer15"],
    )
    with pytest.raises(Wo16ApplicationError, match="WO15_NOT_CURRENT"):
        IntradayWo16Application().execute(request)


@pytest.mark.parametrize(
    "fact",
    ("closed", "ended", "non_trading", "mismatch"),
)
def test_invalid_domain008_session_fails_closed(tmp_path, fact) -> None:  # type: ignore[no-untyped-def]
    chain = _chain(tmp_path)
    source = chain["session15"]
    if fact == "closed":
        value = _fact(
            chain, observed_at=source.session_opens_at - timedelta(seconds=1)
        )
        expected = "DOMAIN_008_NOT_OPEN"
    elif fact == "ended":
        value = _fact(
            chain, observed_at=source.session_closes_at + timedelta(seconds=1)
        )
        expected = "DOMAIN_008_SESSION_ENDED"
    elif fact == "non_trading":
        from kronos.market.schedule import TradingDayStatus

        value = _fact(chain, status=TradingDayStatus.NON_TRADING)
        expected = "DOMAIN_008_NON_TRADING_DAY"
    else:
        value = _fact(chain, calendar="FOREIGN-CALENDAR")
        expected = "CALENDAR_IDENTITY_MISMATCH"
    request = _request(
        chain,
        domain_008_session_fact=value,
        snapshot_timestamp=value.observed_at + timedelta(seconds=1),
        decision_timestamp=value.observed_at + timedelta(seconds=2),
        admission_recorded_at=value.observed_at + timedelta(seconds=3),
    )
    with pytest.raises(Wo16ApplicationError, match=expected):
        IntradayWo16Application().execute(request)


def test_nse_and_mcx_lineage_are_preserved(tmp_path) -> None:
    nse = _chain(tmp_path / "nse")
    nse_result = IntradayWo16Application().execute(_request(nse))
    assert nse_result.upstream_lineage.trade_plan.actual_contract_identity is None
    assert nse_result.upstream_lineage.trade_plan.roll_lineage_identity is None

    mcx = _chain(tmp_path / "mcx", mcx=True)
    mcx_result = IntradayWo16Application().execute(_request(mcx))
    source = mcx["handoff13"]
    bound = mcx_result.upstream_lineage.trade_plan
    assert bound.actual_contract_identity == source.actual_contract_identity
    assert bound.contract_expiry == source.contract_expiry
    assert bound.roll_lineage_identity == source.roll_lineage_identity


def test_instrument_mismatch_and_missing_mcx_lineage_are_rejected(tmp_path) -> None:
    first = _chain(tmp_path / "first")
    second = _chain(tmp_path / "second", mcx=True)
    instrument_mismatch = _request(
        first,
        wo13_source_handoff=second["handoff13"],
    )
    with pytest.raises(Wo16ApplicationError):
        IntradayWo16Application().execute(instrument_mismatch)

    trade = _copy_slots(second["handoff13"])
    object.__setattr__(trade, "actual_contract_identity", None)
    invalid_mcx = _copy_slots(_request(second))
    object.__setattr__(invalid_mcx, "wo13_source_handoff", trade)
    with pytest.raises(Wo16ApplicationError, match="WO16_REQUEST_INVALID"):
        IntradayWo16Application().execute(invalid_mcx)


def test_timezone_naive_timestamp_is_rejected(tmp_path) -> None:
    chain = _chain(tmp_path)
    with pytest.raises(Wo16ApplicationError, match="WO16_REQUEST_INVALID"):
        _request(
            chain,
            decision_timestamp=chain["observed_at"].replace(tzinfo=None),
        )


def test_nonblocking_busy_outcome_creates_no_decision(tmp_path) -> None:
    chain = _chain(tmp_path)
    application = IntradayWo16Application()
    request = _request(chain)
    assert application._lock.acquire(blocking=False)  # noqa: SLF001
    try:
        result = application.execute(request)
    finally:
        application._lock.release()  # noqa: SLF001
    assert type(result) is Wo16BusyOutcome
    assert result.outcome is Wo16ApplicationOutcome.BUSY
    assert not result.decision_created and not result.admission_created


def test_output_has_no_position_fill_quantity_economics_or_execution(tmp_path) -> None:
    result = IntradayWo16Application().execute(_request(_chain(tmp_path)))
    forbidden = {
        "position",
        "fill",
        "quantity",
        "pnl",
        "realised_r",
        "order",
        "broker",
        "execution",
    }
    names = set(_slot_names(result)) | set(_slot_names(result.admission))
    assert not any(name in forbidden for name in names)
    assert not result.admission.position_authority
    assert not result.admission.fill_authority
    assert not result.admission.quantity_authority
    assert not result.admission.execution_authority
    assert not result.admission.broker_authority


def test_application_has_no_hidden_store_or_forbidden_dependency() -> None:
    application = IntradayWo16Application()
    assert set(vars(application)) == {"_lock"}
    assert not hasattr(application, "store")
    assert not hasattr(application, "restore")
    assert IntradayWo16Application.__module__ == (
        "kronos.application.intraday_wo16"
    )


def test_request_and_result_are_immutable_and_deterministic(tmp_path) -> None:
    chain = _chain(tmp_path)
    request = _request(chain)
    second = _request(chain)
    assert request == second
    assert request.request_identity == second.request_identity
    result = IntradayWo16Application().execute(request)
    with pytest.raises(FrozenInstanceError):
        request.choice = Wo16SponsorDecision.LIVE
    with pytest.raises(FrozenInstanceError):
        result.replayed = True


def _copy_slots(value):  # type: ignore[no-untyped-def]
    copied = object.__new__(type(value))
    for name in _slot_names(value):
        object.__setattr__(copied, name, getattr(value, name))
    return copied


def _wo14_state(chain, state):  # type: ignore[no-untyped-def]
    from kronos.intraday.wo14 import _identity as wo14_identity

    observation_values = {
        name: getattr(chain["observation14"], name)
        for name in _slot_names(chain["observation14"])
        if name not in {"observation_identity", "observation_integrity"}
    }
    observation_values["state"] = state
    observation_type = type(chain["observation14"])
    observation = observation_type(
        observation_identity=wo14_identity(
            "INTRADAY-WO14-RISK-OBSERVATION-", observation_values
        ),
        observation_integrity=wo14_identity(
            "INTEGRITY-INTRADAY-WO14-RISK-OBSERVATION-", observation_values
        ),
        **observation_values,
    )
    pointer_values = {
        name: getattr(chain["pointer14"], name)
        for name in _slot_names(chain["pointer14"])
        if name not in {"pointer_identity", "pointer_integrity"}
    }
    pointer_values.update(
        observation_identity=observation.observation_identity,
        observation_integrity=observation.observation_integrity,
        state=state,
    )
    pointer_type = type(chain["pointer14"])
    pointer = pointer_type(
        pointer_identity=wo14_identity(
            "CURRENT-INTRADAY-WO14-V1-", pointer_values
        ),
        pointer_integrity=wo14_identity(
            "INTEGRITY-CURRENT-INTRADAY-WO14-V1-", pointer_values
        ),
        **pointer_values,
    )
    return observation, pointer


def _wo15_state(chain, state):  # type: ignore[no-untyped-def]
    from kronos.intraday.wo15_persistence import _identity as wo15_identity

    values = {
        name: getattr(chain["pointer15"], name)
        for name in _slot_names(chain["pointer15"])
        if name not in {"pointer_identity", "pointer_integrity"}
    }
    values["timing_state"] = state
    pointer_type = type(chain["pointer15"])
    return pointer_type(
        pointer_identity=wo15_identity("CURRENT-INTRADAY-WO15-V1-", values),
        pointer_integrity=wo15_identity(
            "INTEGRITY-CURRENT-INTRADAY-WO15-V1-", values
        ),
        **values,
    )


def _slot_names(value):  # type: ignore[no-untyped-def]
    return tuple(
        name
        for cls in type(value).__mro__
        for name in getattr(cls, "__slots__", ())
        if name not in {"__dict__", "__weakref__"}
    )
