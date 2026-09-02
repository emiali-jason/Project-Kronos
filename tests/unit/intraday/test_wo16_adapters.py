from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import Wo13GeometryAvailability
from kronos.intraday.wo14 import Wo14ObservationState
from kronos.intraday.wo15 import Wo15TimingState
from kronos.intraday.wo16 import (
    WO16_POLICY_CHECKSUM,
    Wo16ContractError,
    canonical_document_bytes,
)
from kronos.intraday.wo16_adapters import (
    Wo16BindingFailure,
    Wo16BindingRejected,
    bind_wo16_risk_observation,
    bind_wo16_session_fact,
    bind_wo16_timing_handoff,
    bind_wo16_trade_plan,
    bind_wo16_upstream,
    is_wo16_risk_state_admissible,
    is_wo16_timing_state_eligible,
)
from kronos.market.schedule import (
    InMemoryMarketScheduleSource,
    MarketDaySchedule,
    MarketSessionService,
    MarketWindow,
    TradingDayStatus,
)

from .test_wo16_contracts import _chain


def _fact(chain, *, exchange=None, day=None, session=None, calendar=None, version=None, observed_at=None, status=TradingDayStatus.TRADING):  # type: ignore[no-untyped-def]
    source = chain["session15"]
    actual_day = day or source.trading_date
    windows = (
        tuple(MarketWindow(*item) for item in source.windows)
        if status is TradingDayStatus.TRADING and actual_day == source.trading_date
        else (
            MarketWindow(
                source.session_opens_at + timedelta(days=1),
                source.session_closes_at + timedelta(days=1),
            ),
        )
        if status is TradingDayStatus.TRADING
        else ()
    )
    schedule = MarketDaySchedule(
        exchange=exchange or source.exchange,
        trading_date=actual_day,
        session_id=session or source.session_identity,
        timezone="Asia/Kolkata",
        status=status,
        windows=windows,
        source_identity=calendar or source.calendar_identity,
        source_version=version or source.calendar_version,
    )
    moment = observed_at
    if moment is None:
        moment = (
            source.session_opens_at + timedelta(minutes=1)
            if actual_day == source.trading_date
            else source.session_opens_at + timedelta(days=1, minutes=1)
        )
    return MarketSessionService(
        InMemoryMarketScheduleSource((schedule,))
    ).facts(
        exchange=schedule.exchange,
        trading_date=schedule.trading_date,
        observed_at=moment,
    )


def test_exact_wo13_wo14_wo15_domain008_graph_is_preserved(tmp_path) -> None:
    chain = _chain(tmp_path)
    trade = chain["trade"]
    risk = chain["risk"]
    timing = chain["timing"]
    session = chain["session"]
    assert trade.trade_plan_identity == chain["plan"].trade_plan_identity
    assert trade.trade_plan_integrity == chain["plan"].trade_plan_integrity
    assert risk.observation_identity == chain["observation14"].observation_identity
    assert risk.observation_integrity == chain["observation14"].observation_integrity
    assert timing.handoff_identity == chain["handoff15"].handoff_identity
    assert timing.handoff_integrity == chain["handoff15"].handoff_integrity
    assert session.session_identity == chain["session15"].session_identity
    assert session.calendar_identity == chain["session15"].calendar_identity
    assert chain["lineage"].policy.policy_checksum == WO16_POLICY_CHECKSUM


def test_wo13_geometry_is_copied_exactly_not_recalculated(tmp_path) -> None:
    chain = _chain(tmp_path)
    plan = chain["plan"]
    binding = chain["trade"]
    assert binding.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE
    assert (
        binding.entry_reference,
        binding.entry_condition,
        binding.stop,
        binding.thesis_invalidation_reference,
        binding.thesis_invalidation_event,
        binding.canonical_target,
        binding.risk_distance,
        binding.reward_distance,
        binding.model_rr,
    ) == (
        plan.entry_reference,
        plan.entry_condition,
        plan.stop,
        plan.thesis_invalidation_reference,
        plan.thesis_invalidation_event,
        plan.canonical_target,
        plan.risk_distance,
        plan.reward_distance,
        plan.model_rr,
    )


def test_stale_wo13_pointer_and_corrupt_integrity_fail_closed(tmp_path) -> None:
    chain = _chain(tmp_path)
    stale = object.__new__(type(chain["pointer13"]))
    for name, value in vars_for_slots(chain["pointer13"]).items():
        object.__setattr__(stale, name, value)
    object.__setattr__(stale, "trade_plan_identity", "FOREIGN-PLAN")
    with pytest.raises(Wo16BindingRejected) as found:
        bind_wo16_trade_plan(
            current_pointer=stale,
            trade_plan=chain["plan"],
            source_handoff=chain["handoff13"],
        )
    assert found.value.failure is Wo16BindingFailure.WO13_INTEGRITY_INVALID


def test_incomplete_geometry_is_not_admission_eligible(tmp_path) -> None:
    chain = _chain(tmp_path)
    plan = object.__new__(type(chain["plan"]))
    for name, value in vars_for_slots(chain["plan"]).items():
        object.__setattr__(plan, name, value)
    object.__setattr__(plan, "geometry_availability", Wo13GeometryAvailability.GEOMETRY_PARTIAL)
    with pytest.raises(Wo16BindingRejected) as found:
        bind_wo16_trade_plan(
            current_pointer=chain["pointer13"],
            trade_plan=plan,
            source_handoff=chain["handoff13"],
        )
    assert found.value.failure is Wo16BindingFailure.WO13_INTEGRITY_INVALID


@pytest.mark.parametrize("state", tuple(Wo14ObservationState))
def test_every_governed_wo14_state_is_advisory_and_admissible(state) -> None:  # type: ignore[no-untyped-def]
    assert is_wo16_risk_state_admissible(state)


def test_wo14_binding_cannot_veto_permit_time_size_or_execute(tmp_path) -> None:
    risk = _chain(tmp_path)["risk"]
    assert risk.authority == "RISK_OBSERVATION_ONLY"
    assert not any(
        (
            risk.trade_permission_authority,
            risk.trade_veto_authority,
            risk.timing_authority,
            risk.sizing_authority,
            risk.final_quantity_authority,
            risk.execution_authority,
        )
    )


def test_wo14_wrong_plan_binding_is_rejected(tmp_path) -> None:
    first = _chain(tmp_path / "first")
    second = _chain(tmp_path / "second", direction=SemanticDirection.SHORT)
    with pytest.raises(Wo16BindingRejected) as found:
        bind_wo16_risk_observation(
            current_pointer=first["pointer14"],
            observation=first["observation14"],
            trade_plan=second["trade"],
        )
    assert found.value.failure in {
        Wo16BindingFailure.WO14_NOT_CURRENT,
        Wo16BindingFailure.WO14_PLAN_MISMATCH,
    }


@pytest.mark.parametrize(
    ("state", "eligible"),
    (
        (Wo15TimingState.TIMING_NOT_EVALUATED, False),
        (Wo15TimingState.TIMING_WAITING, False),
        (Wo15TimingState.TIMING_QUALIFIED, True),
        (Wo15TimingState.TIMING_FAILED, False),
        (Wo15TimingState.TIMING_EXPIRED, False),
        (Wo15TimingState.TIMING_UNAVAILABLE, False),
    ),
)
def test_only_exact_timing_qualified_is_eligible(state, eligible) -> None:  # type: ignore[no-untyped-def]
    assert is_wo16_timing_state_eligible(state) is eligible


def test_wo15_handoff_preserves_completed_5m_and_supersession_fields(tmp_path) -> None:
    chain = _chain(tmp_path)
    source = chain["handoff15"]
    bound = chain["timing"]
    assert bound.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert bound.completed_five_minute_evidence_identity == (
        source.completed_five_minute_evidence_identity
    )
    assert bound.completed_five_minute_evidence_integrity == (
        source.completed_five_minute_evidence_integrity
    )
    assert bound.predecessor_handoff_identity == source.predecessor_handoff_identity
    assert bound.supersession_lineage_identity == source.supersession_lineage_identity


def test_open_current_domain008_session_is_accepted(tmp_path) -> None:
    chain = _chain(tmp_path)
    assert chain["session"].session_open is True
    assert chain["session"].session_end is False
    assert chain["session"].market_session_state.value == "OPEN"


def test_domain008_unavailable_fails_closed(tmp_path) -> None:
    chain = _chain(tmp_path)
    source = chain["session15"]
    fact = MarketSessionService(InMemoryMarketScheduleSource(())).facts(
        exchange=source.exchange,
        trading_date=source.trading_date,
        observed_at=source.session_opens_at,
    )
    with pytest.raises(Wo16BindingRejected) as found:
        bind_wo16_session_fact(
            wo15_session=source, fact=fact, timing_handoff=chain["timing"]
        )
    assert found.value.failure is Wo16BindingFailure.DOMAIN_008_UNAVAILABLE


def test_non_trading_day_fails_closed(tmp_path) -> None:
    chain = _chain(tmp_path)
    fact = _fact(chain, status=TradingDayStatus.NON_TRADING)
    with pytest.raises(Wo16BindingRejected) as found:
        bind_wo16_session_fact(
            wo15_session=chain["session15"],
            fact=fact,
            timing_handoff=chain["timing"],
        )
    assert found.value.failure is Wo16BindingFailure.DOMAIN_008_NON_TRADING_DAY


@pytest.mark.parametrize(
    ("offset", "failure"),
    (
        (timedelta(minutes=-1), Wo16BindingFailure.DOMAIN_008_NOT_OPEN),
        (timedelta(seconds=1), Wo16BindingFailure.DOMAIN_008_SESSION_ENDED),
    ),
)
def test_closed_or_ended_session_fails_closed(tmp_path, offset, failure) -> None:  # type: ignore[no-untyped-def]
    chain = _chain(tmp_path)
    source = chain["session15"]
    moment = (
        source.session_opens_at + offset
        if offset.total_seconds() < 0
        else source.session_closes_at + offset
    )
    fact = _fact(chain, observed_at=moment)
    with pytest.raises(Wo16BindingRejected) as found:
        bind_wo16_session_fact(
            wo15_session=source, fact=fact, timing_handoff=chain["timing"]
        )
    assert found.value.failure is failure


@pytest.mark.parametrize(
    ("changes", "failure"),
    (
        ({"exchange": "MCX"}, Wo16BindingFailure.EXCHANGE_MISMATCH),
        ({"session": "FOREIGN-SESSION"}, Wo16BindingFailure.SESSION_IDENTITY_MISMATCH),
        ({"calendar": "FOREIGN-CALENDAR"}, Wo16BindingFailure.CALENDAR_IDENTITY_MISMATCH),
        ({"version": "FOREIGN-VERSION"}, Wo16BindingFailure.CALENDAR_VERSION_MISMATCH),
    ),
)
def test_domain008_lineage_mismatches_fail_closed(tmp_path, changes, failure) -> None:  # type: ignore[no-untyped-def]
    chain = _chain(tmp_path)
    fact = _fact(chain, **changes)
    with pytest.raises(Wo16BindingRejected) as found:
        bind_wo16_session_fact(
            wo15_session=chain["session15"],
            fact=fact,
            timing_handoff=chain["timing"],
        )
    assert found.value.failure is failure


def test_nse_identity_is_preserved_and_has_no_contract_roll(tmp_path) -> None:
    chain = _chain(tmp_path)
    assert chain["trade"].market_family is not IntradayMarketFamily.MCX
    assert chain["trade"].instrument_identity == chain["plan"].instrument_identity
    assert chain["trade"].actual_contract_identity is None
    assert chain["trade"].roll_lineage_identity is None


def test_mcx_actual_contract_expiry_and_roll_lineage_are_exact(tmp_path) -> None:
    chain = _chain(tmp_path, mcx=True)
    source = chain["handoff13"]
    assert chain["trade"].market_family is IntradayMarketFamily.MCX
    assert chain["trade"].actual_contract_identity == source.actual_contract_identity
    assert chain["trade"].contract_expiry == source.contract_expiry
    assert chain["trade"].roll_lineage_identity == source.roll_lineage_identity
    assert chain["timing"].actual_contract_identity == source.actual_contract_identity
    assert chain["timing"].roll_lineage_identity == source.roll_lineage_identity


def test_missing_mcx_contract_or_roll_cannot_form_valid_binding(tmp_path) -> None:
    trade = _chain(tmp_path, mcx=True)["trade"]
    with pytest.raises(Wo16ContractError, match="WO16_WO13_BINDING_INVALID"):
        object_values = vars_for_slots(trade)
        object_values["actual_contract_identity"] = None
        type(trade)(**object_values)


def test_upstream_lineage_is_immutable_and_deterministic(tmp_path) -> None:
    chain = _chain(tmp_path)
    second = bind_wo16_upstream(
        trade_plan=chain["trade"],
        risk_observation=chain["risk"],
        timing_handoff=chain["timing"],
        session=chain["session"],
    )
    assert second == chain["lineage"]
    assert canonical_document_bytes(second) == canonical_document_bytes(chain["lineage"])
    with pytest.raises(FrozenInstanceError):
        second.lineage_identity = "CHANGED"


def test_no_provider_browser_runtime_or_persistence_dependencies() -> None:
    modules = {
        bind_wo16_trade_plan.__module__,
        bind_wo16_risk_observation.__module__,
        bind_wo16_timing_handoff.__module__,
        bind_wo16_session_fact.__module__,
    }
    assert modules == {"kronos.intraday.wo16_adapters"}


def test_non_enum_timing_and_risk_states_fail_closed() -> None:
    with pytest.raises(Wo16BindingRejected):
        is_wo16_timing_state_eligible("TIMING_QUALIFIED")  # type: ignore[arg-type]
    with pytest.raises(Wo16BindingRejected):
        is_wo16_risk_state_admissible("RISK_OBSERVED")


def vars_for_slots(value: object) -> dict[str, object]:
    return {
        name: getattr(value, name)
        for cls in type(value).__mro__
        for name in getattr(cls, "__slots__", ())
        if isinstance(name, str) and hasattr(value, name)
    }
