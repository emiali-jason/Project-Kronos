from dataclasses import replace
from decimal import Decimal

import pytest

from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.native_trade_construction import construct_trade_plan
from kronos.swing.v1.sponsor_observation_decision import (
    LocalSponsorObservationDecisionStore,
    SPONSOR_DECISION_SNAPSHOT_CONTRACT_ID,
    SPONSOR_OBSERVATION_DECISION_CONTRACT_ID,
    SponsorActivationDisposition,
    SponsorObservationReason,
    journal_observation_handoff,
    record_sponsor_observation_decision,
    transition_sponsor_observation_activation,
)
from kronos.swing.v1.step31_observation import (
    Step31WarningSeverity,
    construct_step31_observation,
    create_sponsor_observation_handoff,
)
from tests.unit.swing.v1.test_kr370_step31_handoff import (
    NOW,
    _completed,
    _context,
    _evidence,
    _handoff,
    _price,
)
from tests.unit.swing.v1.test_step31_observation import _observe, _package


def _green(tmp_path):  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    handoff = _handoff(completed)
    evidence = _evidence(completed)
    context = _context(completed.requirement.canonical_instrument)
    plan = construct_trade_plan(
        completed.requirement, handoff, evidence, context, created_at=NOW
    )
    observation = construct_step31_observation(
        completed.requirement,
        handoff,
        evidence,
        context,
        created_at=NOW,
        conventional_plan=plan,
    )
    return completed, observation


def _red(tmp_path):  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    evidence = _package(
        completed,
        governing_structural_low=_price(
            "RED-NON-POSITIVE-RISK", "105", completed.promotion.analysis_boundary
        ),
    )
    return completed, _observe(completed, evidence)


def _record(
    completed, observation, choice, disposition,  # type: ignore[no-untyped-def]
    *, risk_state="RISK_UNAVAILABLE", acknowledged=False, **changes,
):
    handoff = create_sponsor_observation_handoff(
        observation,
        risk_state=risk_state,
        risk_evidence_identity=changes.get("risk_identity"),
    )
    return record_sponsor_observation_decision(
        completed.promotion,
        observation,
        handoff,
        choice,
        disposition,
        current_run_identity=completed.requirement.native_run_identity,
        decided_at=NOW,
        warning_acknowledged=acknowledged,
        risk_state=risk_state,
        **changes,
    )


def test_green_paper_and_live_can_record_activated_position_lineage(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _green(tmp_path)
    paper = _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.ACTIVATED,
        risk_state="RISK_APPROVED",
        risk_identity="RISK-PAPER",
        existing_sponsor_decision_identity="SPONSOR-DECISION-PAPER",
        sponsor_position_identity="SPONSOR-POSITION-PAPER",
    )
    live = _record(
        completed,
        observation,
        SponsorTradeChoice.LIVE,
        SponsorActivationDisposition.ACTIVATED,
        risk_state="RISK_APPROVED",
        risk_identity="RISK-LIVE",
        existing_sponsor_decision_identity="SPONSOR-DECISION-LIVE",
        sponsor_position_identity="SPONSOR-POSITION-LIVE",
    )

    assert paper.snapshot.contract_identity == SPONSOR_DECISION_SNAPSHOT_CONTRACT_ID
    assert live.decision.contract_identity == SPONSOR_OBSERVATION_DECISION_CONTRACT_ID
    assert paper.activation.disposition is SponsorActivationDisposition.ACTIVATED
    assert live.activation.sponsor_position_identity == "SPONSOR-POSITION-LIVE"


@pytest.mark.parametrize("choice", [SponsorTradeChoice.PAPER, SponsorTradeChoice.LIVE])
def test_red_decision_is_recorded_but_risk_unavailable_blocks_activation(
    tmp_path, choice  # type: ignore[no-untyped-def]
) -> None:
    completed, observation = _red(tmp_path)
    result = _record(
        completed,
        observation,
        choice,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
        acknowledged=True,
        sponsor_reason=SponsorObservationReason.STEP31_WARNING,
    )

    assert result.decision.choice is choice
    assert result.decision.warning_acknowledged
    assert result.snapshot.step31_severity is Step31WarningSeverity.RED
    assert result.snapshot.target == Decimal("120.00")
    assert result.snapshot.risk_reward_state == "INVALID"
    assert result.activation.disposition is SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE
    assert result.activation.sponsor_position_identity is None


def test_red_ignore_is_first_class_without_acknowledgement_or_position(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _red(tmp_path)
    result = _record(
        completed,
        observation,
        SponsorTradeChoice.IGNORE,
        SponsorActivationDisposition.NOT_APPLICABLE_IGNORE,
    )

    assert result.decision.choice is SponsorTradeChoice.IGNORE
    assert not result.decision.warning_acknowledged
    assert result.activation.disposition is SponsorActivationDisposition.NOT_APPLICABLE_IGNORE
    assert result.activation.sponsor_position_identity is None


def test_red_paper_and_live_require_warning_acknowledgement(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _red(tmp_path)
    for choice in (SponsorTradeChoice.PAPER, SponsorTradeChoice.LIVE):
        with pytest.raises(ValueError, match="ACKNOWLEDGEMENT_REQUIRED"):
            _record(
                completed,
                observation,
                choice,
                SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
            )


@pytest.mark.parametrize("severity", ["RISK_REJECTED", "RISK_UNAVAILABLE"])
def test_risk_hard_gate_is_retained_without_rewriting_sponsor_choice(
    tmp_path, severity  # type: ignore[no-untyped-def]
) -> None:
    completed, observation = _green(tmp_path)
    disposition = (
        SponsorActivationDisposition.BLOCKED_RISK_REJECTED
        if severity == "RISK_REJECTED"
        else SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE
    )
    result = _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        disposition,
        risk_state=severity,
        risk_identity="RISK-HARD-GATE" if severity == "RISK_REJECTED" else None,
    )
    assert result.decision.choice is SponsorTradeChoice.PAPER
    assert result.snapshot.risk_state == severity
    assert result.activation.disposition is disposition


def test_constrained_risk_records_choice_but_fails_closed_without_executable_detail(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _green(tmp_path)
    result = _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_CONSTRAINT,
        risk_state="RISK_CONSTRAINED",
        risk_identity="RISK-CONSTRAINED",
    )
    assert result.decision.choice is SponsorTradeChoice.PAPER
    assert result.activation.disposition is SponsorActivationDisposition.BLOCKED_CONSTRAINT
    assert result.activation.sponsor_position_identity is None


def test_foreign_stale_and_corrupt_lineage_create_no_decision(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _green(tmp_path)
    handoff = create_sponsor_observation_handoff(
        observation, risk_state="RISK_UNAVAILABLE", risk_evidence_identity=None
    )
    with pytest.raises(ValueError, match="HANDOFF_INVALID"):
        record_sponsor_observation_decision(
            completed.promotion,
            observation,
            replace(handoff, canonical_instrument="FOREIGN"),
            SponsorTradeChoice.IGNORE,
            SponsorActivationDisposition.NOT_APPLICABLE_IGNORE,
            current_run_identity=completed.requirement.native_run_identity,
            decided_at=NOW,
            warning_acknowledged=False,
        )
    with pytest.raises(ValueError, match="TRUST_BINDING_INVALID"):
        record_sponsor_observation_decision(
            completed.promotion,
            observation,
            handoff,
            SponsorTradeChoice.IGNORE,
            SponsorActivationDisposition.NOT_APPLICABLE_IGNORE,
            current_run_identity="SWING-RUN-" + "F" * 32,
            decided_at=NOW,
            warning_acknowledged=False,
        )


def test_store_is_immutable_restart_safe_queryable_and_journal_ready(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _red(tmp_path)
    paper = _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
        acknowledged=True,
    )
    store = LocalSponsorObservationDecisionStore(tmp_path / "observation-decisions")
    assert store.retain(paper) == paper
    assert store.retain(paper) == paper
    assert store.load_all() == (paper,)
    assert store.by_choice(SponsorTradeChoice.PAPER) == (paper,)
    assert store.by_disposition(
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE
    ) == (paper,)
    assert store.by_severity(Step31WarningSeverity.RED) == (paper,)
    assert store.for_current_observations((observation,)) == (paper,)
    handoff = journal_observation_handoff(paper)
    assert handoff.decision_identity == paper.decision.decision_identity
    assert handoff.sponsor_position_identity is None

    changed = _record(
        completed,
        observation,
        SponsorTradeChoice.LIVE,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
        acknowledged=True,
    )
    with pytest.raises(ValueError, match="ALREADY_FINAL"):
        store.retain(changed)


def test_pending_entry_transition_preserves_decision_and_restores_terminal_activation(
    tmp_path,
) -> None:
    completed, observation = _green(tmp_path)
    pending = _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION,
        risk_state="RISK_APPROVED",
        risk_identity="RISK-PENDING",
    )
    store = LocalSponsorObservationDecisionStore(tmp_path / "decisions")
    assert store.retain(pending) == pending

    activated = transition_sponsor_observation_activation(
        pending,
        SponsorActivationDisposition.ACTIVATED,
        existing_sponsor_decision_identity="SPONSOR-DECISION-PAPER",
        sponsor_position_identity="SPONSOR-POSITION-PAPER",
        recorded_at=NOW,
    )
    assert store.transition_activation(activated) == activated
    assert store.transition_activation(activated) == activated
    assert store.load_all() == (activated,)
    assert store.load_all_initial() == (pending,)
    assert activated.snapshot == pending.snapshot
    assert activated.decision == pending.decision
