from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.application.intraday_wo16 import IntradayWo16PersistenceApplication
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo15 import Wo15TimingState
from kronos.intraday.wo16 import (
    Wo16LifecycleAdmissionDisposition,
    Wo16SponsorDecision,
)
from kronos.intraday.wo16_persistence import Wo16Store
from kronos.intraday.wo17 import WO17_POLICY_CHECKSUM, canonical_document_bytes
from kronos.intraday.wo17_adapters import (
    Wo17BindingFailure,
    Wo17BindingRejected,
    bind_wo17_upstream,
)

from .test_wo16_application import _request
from .test_wo16_contracts import _chain


def _restored(  # type: ignore[no-untyped-def]
    tmp_path, *, choice=Wo16SponsorDecision.PAPER, mcx=False
):
    chain = _chain(tmp_path / "chain", mcx=mcx)
    request = _request(chain, choice)
    store = Wo16Store((tmp_path / "wo16").resolve())
    IntradayWo16PersistenceApplication(store=store).execute(request)
    restored = store.restore_current(chain["plan"].canonical_subject_identity)
    assert restored is not None
    return chain, restored


def _bind(  # type: ignore[no-untyped-def]
    tmp_path, *, choice=Wo16SponsorDecision.PAPER, mcx=False
):
    chain, restored = _restored(tmp_path, choice=choice, mcx=mcx)
    bound_at = chain["observed_at"] + timedelta(seconds=4)
    snapshot = bind_wo17_upstream(
        current_pointer=restored.pointer,
        snapshot=restored.snapshot,
        decision=restored.decision,
        admission=restored.admission,
        bound_at=bound_at,
    )
    return chain, restored, snapshot


@pytest.mark.parametrize(
    "choice", (Wo16SponsorDecision.PAPER, Wo16SponsorDecision.LIVE)
)
def test_exact_current_wo13_through_wo16_graph_binds(  # type: ignore[no-untyped-def]
    tmp_path, choice
) -> None:
    chain, restored, result = _bind(tmp_path, choice=choice)
    lineage = result.lineage
    assert lineage.wo13_trade_plan_identity == chain["plan"].trade_plan_identity
    assert lineage.wo14_observation_identity == (
        chain["observation14"].observation_identity
    )
    assert lineage.wo15_handoff_identity == chain["handoff15"].handoff_identity
    assert lineage.wo16_decision_identity == restored.decision.decision_identity
    assert lineage.wo16_admission_identity == restored.admission.admission_identity
    assert lineage.domain_008_session_binding_identity == (
        chain["session"].binding_identity
    )
    assert lineage.sponsor_decision is choice
    assert lineage.lifecycle_admission is (
        Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE
    )
    assert lineage.timing_state is Wo15TimingState.TIMING_QUALIFIED
    assert result.policy.policy_checksum == WO17_POLICY_CHECKSUM


def test_trade_geometry_and_decimal_objects_are_copied_exactly(tmp_path) -> None:
    chain, _, result = _bind(tmp_path)
    trade = chain["trade"]
    lineage = result.lineage
    assert (
        lineage.entry_reference,
        lineage.stop,
        lineage.thesis_invalidation_reference,
        lineage.canonical_target,
        lineage.risk_distance,
        lineage.reward_distance,
        lineage.model_rr,
    ) == (
        trade.entry_reference,
        trade.stop,
        trade.thesis_invalidation_reference,
        trade.canonical_target,
        trade.risk_distance,
        trade.reward_distance,
        trade.model_rr,
    )
    assert all(
        type(value) is Decimal
        for value in (
            lineage.entry_reference,
            lineage.stop,
            lineage.canonical_target,
            lineage.model_rr,
        )
    )


def test_nse_lineage_contains_no_invented_mcx_values(tmp_path) -> None:
    _, _, result = _bind(tmp_path)
    lineage = result.lineage
    assert lineage.market_family is not IntradayMarketFamily.MCX
    assert (
        lineage.actual_contract_identity,
        lineage.contract_expiry,
        lineage.roll_lineage_identity,
    ) == (None, None, None)


def test_mcx_actual_contract_expiry_and_roll_lineage_bind_exactly(tmp_path) -> None:
    chain, restored, result = _bind(tmp_path, mcx=True)
    lineage = result.lineage
    assert lineage.market_family is IntradayMarketFamily.MCX
    assert (
        lineage.actual_contract_identity,
        lineage.contract_expiry,
        lineage.roll_lineage_identity,
    ) == (
        chain["trade"].actual_contract_identity,
        chain["trade"].contract_expiry,
        chain["trade"].roll_lineage_identity,
    )
    assert lineage.actual_contract_identity == restored.pointer.actual_contract_identity


def test_ignore_and_not_applicable_admission_are_rejected(tmp_path) -> None:
    chain, restored = _restored(tmp_path, choice=Wo16SponsorDecision.IGNORE)
    with pytest.raises(Wo17BindingRejected) as found:
        bind_wo17_upstream(
            current_pointer=restored.pointer,
            snapshot=restored.snapshot,
            decision=restored.decision,
            admission=restored.admission,
            bound_at=chain["observed_at"] + timedelta(seconds=4),
        )
    assert found.value.failure is Wo17BindingFailure.WO16_DECISION_NOT_ELIGIBLE


def test_foreign_or_superseded_wo16_graph_is_rejected(tmp_path) -> None:
    first_chain, first = _restored(tmp_path / "first")
    _, second = _restored(tmp_path / "second", choice=Wo16SponsorDecision.LIVE)
    with pytest.raises(Wo17BindingRejected) as found:
        bind_wo17_upstream(
            current_pointer=first.pointer,
            snapshot=second.snapshot,
            decision=second.decision,
            admission=second.admission,
            bound_at=first_chain["observed_at"] + timedelta(seconds=4),
        )
    assert found.value.failure is Wo17BindingFailure.WO16_NOT_CURRENT


def test_corrupt_source_integrity_fails_closed_with_sanitized_code(tmp_path) -> None:
    chain, restored = _restored(tmp_path)
    corrupt = object.__new__(type(restored.decision))
    for name in restored.decision.__slots__:
        object.__setattr__(corrupt, name, getattr(restored.decision, name))
    object.__setattr__(corrupt, "decision_integrity", "CORRUPT")
    with pytest.raises(Wo17BindingRejected) as found:
        bind_wo17_upstream(
            current_pointer=restored.pointer,
            snapshot=restored.snapshot,
            decision=corrupt,
            admission=restored.admission,
            bound_at=chain["observed_at"] + timedelta(seconds=4),
        )
    assert found.value.failure is Wo17BindingFailure.SOURCE_CONTRACT_INVALID
    assert str(found.value) == "SOURCE_CONTRACT_INVALID"


def test_closed_session_and_naive_bound_time_fail_closed(tmp_path) -> None:
    _, restored = _restored(tmp_path)
    closes_at = restored.snapshot.upstream_lineage.session.active_window_closes_at
    with pytest.raises(Wo17BindingRejected) as ended:
        bind_wo17_upstream(
            current_pointer=restored.pointer,
            snapshot=restored.snapshot,
            decision=restored.decision,
            admission=restored.admission,
            bound_at=closes_at,
        )
    assert ended.value.failure is Wo17BindingFailure.DOMAIN_008_SESSION_ENDED
    with pytest.raises(Wo17BindingRejected) as naive:
        bind_wo17_upstream(
            current_pointer=restored.pointer,
            snapshot=restored.snapshot,
            decision=restored.decision,
            admission=restored.admission,
            bound_at=closes_at.replace(tzinfo=None),
        )
    assert naive.value.failure is Wo17BindingFailure.SOURCE_CONTRACT_INVALID


def test_non_closed_position_blocks_successor_without_mutating_either_graph(
    tmp_path,
) -> None:
    chain, restored = _restored(tmp_path)
    before = canonical_document_bytes(restored)
    with pytest.raises(Wo17BindingRejected) as found:
        bind_wo17_upstream(
            current_pointer=restored.pointer,
            snapshot=restored.snapshot,
            decision=restored.decision,
            admission=restored.admission,
            bound_at=chain["observed_at"] + timedelta(seconds=4),
            existing_non_closed_position_identity="INTRADAY-WO17-POSITION-PRIOR",
        )
    assert found.value.failure is Wo17BindingFailure.NON_CLOSED_POSITION_EXISTS
    assert canonical_document_bytes(restored) == before


def test_slice1_snapshot_is_immutable_and_has_no_position_or_execution_truth(
    tmp_path,
) -> None:
    _, _, result = _bind(tmp_path)
    assert result.position_identity is None
    assert result.current_position_pointer_identity is None
    assert (result.fill, result.quantity, result.monetary_pnl, result.realised_r) == (
        "UNAVAILABLE",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "UNAVAILABLE",
    )
    assert not any(
        value
        for name, value in asdict(result).items()
        if name.endswith("_authority") and type(value) is bool
    )
    with pytest.raises(FrozenInstanceError):
        result.position_identity = "POSITION"


def test_same_facts_are_deterministic_and_unknown_fields_are_rejected(tmp_path) -> None:
    chain, restored = _restored(tmp_path)
    arguments = {
        "current_pointer": restored.pointer,
        "snapshot": restored.snapshot,
        "decision": restored.decision,
        "admission": restored.admission,
        "bound_at": chain["observed_at"] + timedelta(seconds=4),
    }
    first = bind_wo17_upstream(**arguments)
    second = bind_wo17_upstream(**arguments)
    assert first == second
    assert first.snapshot_identity == second.snapshot_identity
    values = asdict(first)
    values["unexpected"] = "REJECT"
    with pytest.raises(TypeError):
        type(first)(**values)
