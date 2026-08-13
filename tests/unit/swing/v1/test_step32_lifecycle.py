from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import json

import pytest

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.provider.contracts.monitoring import (
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)
from kronos.swing.v1.step32 import (
    Availability,
    CandidateLifecycleState,
    EntryOutcomeState,
    Freshness,
    LifecycleEventType,
    LocalStep32Store,
    ModelCloseReason,
    MonitoringAdmissionContext,
    MonitoringAdmissionRegistry,
    MonitoringSubmissionType,
    ObjectiveModelState,
    RecoveryState,
    RiskConstraints,
    RiskState,
    SponsorDecisionMode,
    SponsorExecutionEvidence,
    SponsorOrderEvidence,
    SponsorPositionState,
    activate_objective_model,
    build_completed_daily_submission,
    build_monitoring_submission,
    candidate_digest,
    create_business_judgment,
    create_sponsor_position,
    evaluate_entry_timing,
    evaluate_objective_model,
    freeze_sponsor_decision,
    publish_lifecycle_event,
    project_paper_position_closure,
    publish_live_action_required,
    record_risk_result,
    record_sponsor_decision,
    record_sponsor_order_evidence,
    recover_objective_model,
    start_candidate_lifecycle,
    transition_candidate_lifecycle,
)
from kronos.swing.v1.trade_construction import construct_trade_candidate
from tests.unit.swing.v1.test_trade_construction import _input


_NOW = datetime.fromisoformat("2026-08-13T12:00:00+05:30")
_BOUNDARY = datetime.fromisoformat("2026-08-12T00:00:00+05:30")
_INSTRUMENT = InstrumentRecord(
    "KITE",
    "NSE",
    "NSE",
    "RELIANCE",
    "RELIANCE",
    "EQ",
    None,
)
_MCX_INSTRUMENT = InstrumentRecord(
    "KITE",
    "MCX",
    "MCX-FUT",
    "GOLDM26AUGFUT",
    "GOLDM",
    "FUT",
    datetime(2026, 8, 28).date(),
)


def _candidate():  # type: ignore[no-untyped-def]
    return construct_trade_candidate(_input(), clock=_NOW)


def _judgment(candidate=None):  # type: ignore[no-untyped-def]
    actual = candidate or _candidate()
    return create_business_judgment(
        actual,
        validation_identity="SWING-V1-VALIDATION-20260813",
        clock=_NOW,
    )


def _risk(candidate=None, state=RiskState.APPROVED):  # type: ignore[no-untyped-def]
    actual = candidate or _candidate()
    constraints = RiskConstraints(maximum_quantity=Decimal("10")) if state is RiskState.CONSTRAINED else None
    return record_risk_result(
        actual,
        _judgment(actual),
        state,
        constraints=constraints,
        reason=state.value,
        clock=_NOW,
    )


def _lifecycle(candidate=None, risk=None):  # type: ignore[no-untyped-def]
    actual = candidate or _candidate()
    actual_risk = risk or _risk(actual)
    return start_candidate_lifecycle(
        actual,
        actual_risk,
        monitoring_binding_id="MONITORING-BINDING-20260813",
        clock=_NOW,
    )


def _submission(candidate, lifecycle, price: str | None, sequence: int, **changes):  # type: ignore[no-untyped-def]
    instrument = changes.pop("instrument", _INSTRUMENT)
    submission_type = changes.get(
        "submission_type",
        MonitoringSubmissionType.ENTRY_LEVEL_CROSSED,
    )
    tick_fields = {
        "observed_at": changes.pop("observed_at", _NOW + timedelta(minutes=sequence)),
        "source_sequence": changes.pop("source_sequence", sequence),
        "previous_interval_available": changes.pop("previous_interval_available", True),
        "session_continuous": changes.pop("session_continuous", True),
        "ordering_deterministic": changes.pop("ordering_deterministic", True),
    }
    tick = ProviderMarketTick(
        instrument,
        Decimal(price or "0"),
        tick_fields["observed_at"],
        tick_fields["observed_at"] + timedelta(seconds=1),
        "KITE_CONNECT_WEBSOCKET",
        "KITE-WS-CONNECTION-1",
        tick_fields["source_sequence"],
        tick_fields["previous_interval_available"],
        tick_fields["session_continuous"],
        tick_fields["ordering_deterministic"],
    )
    values = {
        "submission_id": f"SUBMISSION-{sequence}",
        "candidate_id": candidate.candidate_id,
        "monitoring_binding_id": lifecycle.monitoring_binding_id,
        "model_trade_id": None,
        "product": candidate.product,
        "direction": candidate.direction,
        "submission_type": MonitoringSubmissionType.ENTRY_LEVEL_CROSSED,
        "reference": "ENTRY-REFERENCE",
        "boundary": _BOUNDARY,
        "timeframe": "DAILY",
        "session_identity": "NSE-20260813",
    }
    values.update(changes)
    if submission_type is MonitoringSubmissionType.DAILY_BOUNDARY_CLOSED:
        return build_completed_daily_submission(
            HistoricalCandle(
                tick_fields["observed_at"],
                float(price or "0"),
                float(price or "0"),
                float(price or "0"),
                float(price or "0"),
                0,
            ),
            instrument,
            submission_id=values["submission_id"],
            candidate_id=values["candidate_id"],
            monitoring_binding_id=values["monitoring_binding_id"],
            model_trade_id=values["model_trade_id"],
            product=values["product"],
            direction=values["direction"],
            reference=values["reference"],
            boundary=values["boundary"],
            session_identity=values["session_identity"],
            source_request_id="KITE-HISTORICAL-REQUEST-1",
        )
    return build_monitoring_submission(tick, **values)


def _context(
    candidate,
    lifecycle,
    *,
    model_trade_id=None,
    provider_source="KITE_CONNECT_WEBSOCKET",
    source_connection_id="KITE-WS-CONNECTION-1",
):  # type: ignore[no-untyped-def]
    return MonitoringAdmissionContext(
        candidate_id=candidate.candidate_id,
        monitoring_binding_id=lifecycle.monitoring_binding_id,
        model_trade_id=model_trade_id,
        canonical_instrument=candidate.canonical_instrument,
        provider_instrument="NSE:RELIANCE",
        product=candidate.product,
        direction=candidate.direction,
        provider_source=provider_source,
        source_connection_id=source_connection_id,
        binding_active=True,
        boundary=_BOUNDARY,
        timeframe="DAILY",
        session_identity="NSE-20260813",
    )


def _entry_fixture():  # type: ignore[no-untyped-def]
    candidate = _candidate()
    risk = _risk(candidate)
    lifecycle = _lifecycle(candidate, risk)
    registry = MonitoringAdmissionRegistry()
    previous = registry.admit(_submission(candidate, lifecycle, "99.00", 1), _context(candidate, lifecycle), clock=_NOW)
    current = registry.admit(_submission(candidate, lifecycle, str(candidate.entry_price), 2), _context(candidate, lifecycle), clock=_NOW)
    outcome = evaluate_entry_timing(candidate, risk, lifecycle, previous, current)
    return candidate, risk, lifecycle, registry, outcome


def test_business_judgment_binds_immutable_candidate_without_geometry() -> None:
    candidate = _candidate()
    judgment = create_business_judgment(
        candidate,
        validation_identity="SWING-V1-VALIDATION-20260813",
        canonical_instrument_echo=candidate.canonical_instrument,
        product_echo=candidate.product,
        setup_echo=candidate.setup_family,
        direction_echo=candidate.direction,
        clock=_NOW,
    )
    assert judgment.candidate_digest == candidate_digest(candidate)
    assert not hasattr(judgment, "entry_price")
    assert judgment.freshness is Freshness.CURRENT


def test_business_judgment_echo_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="BOUND_ECHO_MISMATCH"):
        create_business_judgment(
            _candidate(),
            validation_identity="SWING-V1-VALIDATION-20260813",
            direction_echo="SHORT",
        )


@pytest.mark.parametrize("state", tuple(RiskState))
def test_all_approved_risk_states_are_representable(state: RiskState) -> None:
    risk = _risk(state=state)
    assert risk.state is state
    assert risk.permits_entry is (state in {RiskState.APPROVED, RiskState.CONSTRAINED})


def test_risk_constraints_require_explicit_approved_values() -> None:
    candidate = _candidate()
    with pytest.raises(ValueError, match="RISK_CONSTRAINT_REQUIRED"):
        record_risk_result(
            candidate,
            _judgment(candidate),
            RiskState.CONSTRAINED,
            reason="RISK_CONSTRAINED",
        )
    with pytest.raises(ValueError, match="RISK_CONSTRAINT_NOT_APPLICABLE"):
        record_risk_result(
            candidate,
            _judgment(candidate),
            RiskState.APPROVED,
            constraints=RiskConstraints(maximum_quantity=Decimal("1")),
            reason="RISK_APPROVED",
        )


def test_risk_contract_cannot_mutate_trade_geometry() -> None:
    candidate = _candidate()
    risk = _risk(candidate, RiskState.CONSTRAINED)
    assert not any(hasattr(risk, name) for name in ("entry_price", "stop_price", "target_price", "direction", "setup"))
    assert candidate.entry_price == Decimal("100.05")


@pytest.mark.parametrize(
    ("risk_state", "expected"),
    (
        (RiskState.APPROVED, CandidateLifecycleState.WAITING_FOR_ENTRY),
        (RiskState.CONSTRAINED, CandidateLifecycleState.WAITING_FOR_ENTRY),
        (RiskState.REJECTED, CandidateLifecycleState.RISK_REJECTED),
        (RiskState.UNAVAILABLE, CandidateLifecycleState.WAITING_FOR_RISK),
    ),
)
def test_candidate_lifecycle_is_driven_by_risk_without_new_policy(risk_state, expected) -> None:  # type: ignore[no-untyped-def]
    candidate = _candidate()
    assert _lifecycle(candidate, _risk(candidate, risk_state)).state is expected


def test_sponsor_decision_can_be_revised_only_before_entry() -> None:
    candidate = _candidate()
    risk = _risk(candidate)
    lifecycle = _lifecycle(candidate, risk)
    first = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.LIVE, clock=_NOW)
    revised = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.PAPER, previous=first, clock=_NOW)
    assert revised.revision == 2
    frozen = freeze_sponsor_decision(revised)
    with pytest.raises(ValueError, match="REVISION_INVALID"):
        record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.LIVE, previous=frozen)


def test_ignore_and_no_decision_do_not_suppress_objective_entry() -> None:
    candidate, risk, lifecycle, _, outcome = _entry_fixture()
    ignored = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.IGNORE, clock=_NOW)
    ignored_model = activate_objective_model(candidate, risk, outcome)
    no_decision_model = activate_objective_model(candidate, risk, outcome)
    assert ignored.mode is SponsorDecisionMode.IGNORE
    assert ignored_model.state is ObjectiveModelState.ACTIVE
    assert no_decision_model.state is ObjectiveModelState.ACTIVE


def test_kite_order_update_is_sponsor_evidence_only_and_cannot_close_model() -> None:
    candidate, risk, lifecycle, _, outcome = _entry_fixture()
    decision = record_sponsor_decision(
        candidate,
        risk,
        lifecycle,
        SponsorDecisionMode.LIVE,
        clock=_NOW,
    )
    model = activate_objective_model(candidate, risk, outcome)
    update = ProviderOrderUpdateEvidence(
        "ORDER-1",
        _INSTRUMENT,
        "COMPLETE",
        "BUY",
        Decimal("2"),
        Decimal("100.10"),
        _NOW + timedelta(minutes=3),
        _NOW + timedelta(minutes=4),
        "KITE_CONNECT_ORDER_UPDATE",
    )
    evidence = record_sponsor_order_evidence(update, candidate, decision)
    assert type(evidence) is SponsorOrderEvidence
    assert evidence.sponsor_decision_id == decision.sponsor_decision_id
    assert model.state is ObjectiveModelState.ACTIVE
    assert not hasattr(evidence, "close_reason")

    other = replace(candidate, candidate_id="CANDIDATE-WRONG")
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        record_sponsor_order_evidence(update, other, decision)


def test_entry_acceptance_closes_sponsor_revision_window() -> None:
    candidate, risk, lifecycle, _, outcome = _entry_fixture()
    with pytest.raises(ValueError, match="WINDOW_CLOSED"):
        record_sponsor_decision(
            candidate,
            risk,
            lifecycle,
            SponsorDecisionMode.LIVE,
            entry_outcome=outcome,
        )


def test_monitoring_submission_requires_domain_002_admission() -> None:
    candidate = _candidate()
    lifecycle = _lifecycle(candidate)
    submission = _submission(candidate, lifecycle, "99.00", 1)
    assert submission.contract_identity.endswith("MONITORING-SUBMISSION-V1")
    assert not hasattr(submission, "observation_id")
    observation = MonitoringAdmissionRegistry().admit(
        submission,
        _context(candidate, lifecycle),
        clock=_NOW,
    )
    assert observation.contract_identity.endswith("MONITORING-OBSERVATION-V1")
    assert observation.source_submission_id == submission.submission_id
    assert observation.provenance[-1] == "DOMAIN-002"
    assert not hasattr(submission, "pine_hash")
    assert not hasattr(submission, "alert_configuration_id")


def test_monitoring_admission_rejects_wrong_provider_or_instrument_binding() -> None:
    candidate = _candidate()
    lifecycle = _lifecycle(candidate)
    submission = _submission(candidate, lifecycle, "99.00", 1)
    context = _context(candidate, lifecycle)
    with pytest.raises(ValueError, match="BINDING_REJECTED"):
        MonitoringAdmissionRegistry().admit(
            submission,
            replace(context, source_connection_id="KITE-WS-CONNECTION-WRONG"),
        )
    with pytest.raises(ValueError, match="BINDING_REJECTED"):
        MonitoringAdmissionRegistry().admit(
            submission,
            replace(context, canonical_instrument="HDFCBANK"),
        )


def test_monitoring_admission_is_idempotent_and_rejects_conflict() -> None:
    candidate = _candidate()
    lifecycle = _lifecycle(candidate)
    registry = MonitoringAdmissionRegistry()
    context = _context(candidate, lifecycle)
    submission = _submission(candidate, lifecycle, "99.00", 1)
    first = registry.admit(submission, context, clock=_NOW)
    assert registry.admit(submission, context, clock=_NOW) is first
    conflict = _submission(candidate, lifecycle, "98.00", 1)
    with pytest.raises(ValueError, match="SUBMISSION_CONFLICT"):
        registry.admit(conflict, context, clock=_NOW)


def test_entry_crossing_requires_consecutive_ordered_observations() -> None:
    candidate, risk, lifecycle, _, outcome = _entry_fixture()
    assert outcome.state is EntryOutcomeState.ENTRY_TRIGGERED
    assert outcome.model_reference_entry_price == candidate.entry_price
    assert outcome.model_reference_entry_availability is Availability.AVAILABLE


def test_first_observation_beyond_entry_reconciles_without_activation() -> None:
    candidate = _candidate()
    risk = _risk(candidate)
    lifecycle = _lifecycle(candidate, risk)
    current = MonitoringAdmissionRegistry().admit(
        _submission(candidate, lifecycle, str(candidate.entry_price), 1),
        _context(candidate, lifecycle),
    )
    outcome = evaluate_entry_timing(candidate, risk, lifecycle, None, current)
    assert outcome.state is EntryOutcomeState.RECONCILIATION_REQUIRED_PRE_ENTRY
    with pytest.raises(ValueError, match="ACTIVATION_INVALID"):
        activate_objective_model(candidate, risk, outcome)


@pytest.mark.parametrize(
    "continuity_change",
    (
        {"previous_interval_available": False},
        {"session_continuous": False},
        {"ordering_deterministic": False},
    ),
)
def test_entry_crossing_with_missing_gap_or_ambiguous_order_reconciles(continuity_change) -> None:  # type: ignore[no-untyped-def]
    candidate = _candidate()
    risk = _risk(candidate)
    lifecycle = _lifecycle(candidate, risk)
    registry = MonitoringAdmissionRegistry()
    context = _context(candidate, lifecycle)
    previous = registry.admit(_submission(candidate, lifecycle, "99", 1), context)
    current = registry.admit(
        _submission(candidate, lifecycle, str(candidate.entry_price), 2, **continuity_change),
        context,
    )
    assert evaluate_entry_timing(candidate, risk, lifecycle, previous, current).state is EntryOutcomeState.RECONCILIATION_REQUIRED_PRE_ENTRY


def _model_observation(model, candidate, lifecycle, registry, kind, price, sequence, **changes):  # type: ignore[no-untyped-def]
    submission = _submission(
        candidate,
        lifecycle,
        price,
        sequence,
        model_trade_id=model.model_trade_id,
        submission_type=kind,
        reference=f"{kind.value}-REFERENCE",
        **changes,
    )
    return registry.admit(
        submission,
        _context(
            candidate,
            lifecycle,
            model_trade_id=model.model_trade_id,
            provider_source="KITE_CONNECT_HISTORICAL"
            if kind is MonitoringSubmissionType.DAILY_BOUNDARY_CLOSED
            else "KITE_CONNECT_WEBSOCKET",
            source_connection_id="KITE-HISTORICAL-REQUEST-1"
            if kind is MonitoringSubmissionType.DAILY_BOUNDARY_CLOSED
            else "KITE-WS-CONNECTION-1",
        ),
        clock=submission.observed_at,
    )


def _model_fixture():  # type: ignore[no-untyped-def]
    candidate, risk, lifecycle, registry, outcome = _entry_fixture()
    return candidate, risk, lifecycle, registry, outcome, activate_objective_model(candidate, risk, outcome)


def test_stop_closes_objective_model_without_broker_semantics() -> None:
    candidate, _, lifecycle, registry, _, model = _model_fixture()
    stop = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.STOP_LEVEL_CROSSED, "94.00", 3)
    closed = evaluate_objective_model(model, (stop,))
    assert closed.state is ObjectiveModelState.CLOSED
    assert closed.close_reason is ModelCloseReason.STOP
    assert closed.exit_price == Decimal("94.00")
    assert not hasattr(closed, "order_id")


def test_target_closes_at_canonical_target_without_favourable_improvement() -> None:
    candidate, _, lifecycle, registry, _, model = _model_fixture()
    target = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.TARGET_LEVEL_CROSSED, "115.00", 3)
    closed = evaluate_objective_model(model, (target,))
    assert closed.close_reason is ModelCloseReason.TARGET
    assert closed.exit_price == model.target_price


def test_completed_daily_observation_can_establish_analytical_invalidation() -> None:
    candidate, _, lifecycle, registry, _, model = _model_fixture()
    daily = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.DAILY_BOUNDARY_CLOSED, "93.00", 3)
    closed = evaluate_objective_model(model, (daily,))
    assert closed.close_reason is ModelCloseReason.ANALYTICAL_INVALIDATION


def test_ambiguous_stop_target_order_reconciles_or_closes_unresolved() -> None:
    candidate, _, lifecycle, registry, _, model = _model_fixture()
    instant = _NOW + timedelta(minutes=3)
    stop = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.STOP_LEVEL_CROSSED, "94", 3, observed_at=instant, source_sequence=None)
    target = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.TARGET_LEVEL_CROSSED, "113", 4, observed_at=instant, source_sequence=None)
    reconciled = evaluate_objective_model(model, (stop, target))
    unresolved = evaluate_objective_model(model, (stop, target), irrecoverable_ambiguity=True)
    assert reconciled.state is ObjectiveModelState.RECONCILIATION_REQUIRED
    assert unresolved.state is ObjectiveModelState.CLOSED
    assert unresolved.close_reason is ModelCloseReason.OUTCOME_UNRESOLVED


def test_known_authoritative_stop_target_order_resolves_in_order() -> None:
    candidate, _, lifecycle, registry, _, model = _model_fixture()
    instant = _NOW + timedelta(minutes=3)
    stop = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.STOP_LEVEL_CROSSED, "94", 3, observed_at=instant)
    target = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.TARGET_LEVEL_CROSSED, "113", 4, observed_at=instant)
    assert evaluate_objective_model(model, (target, stop)).close_reason is ModelCloseReason.STOP


def test_mcx_nse_instrument_binding_isolation_fails_closed() -> None:
    candidate = _candidate()
    lifecycle = _lifecycle(candidate)
    submission = _submission(candidate, lifecycle, "99", 1, instrument=_MCX_INSTRUMENT)
    with pytest.raises(ValueError, match="BINDING_REJECTED"):
        MonitoringAdmissionRegistry().admit(submission, _context(candidate, lifecycle))


def test_paper_position_does_not_invent_actual_accounting() -> None:
    candidate, risk, lifecycle, _, outcome, model = _model_fixture()
    decision = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.PAPER, clock=_NOW)
    position = create_sponsor_position(decision, candidate, risk, model)
    assert position.state is SponsorPositionState.ACTIVE
    assert position.model_reference_entry_availability is Availability.AVAILABLE
    assert position.actual_entry_availability is Availability.UNAVAILABLE
    assert position.actual_pnl_availability is Availability.UNAVAILABLE
    assert position.actual_r_availability is Availability.UNAVAILABLE


def test_live_position_requires_explicit_actual_evidence() -> None:
    candidate, risk, lifecycle, _, _, model = _model_fixture()
    decision = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.LIVE, clock=_NOW)
    planned = create_sponsor_position(decision, candidate, risk, model)
    evidence = SponsorExecutionEvidence("SPONSOR-EXECUTION-1", Decimal("101"), Decimal("2"), _NOW)
    active = create_sponsor_position(decision, candidate, risk, model, actual_evidence=evidence)
    assert planned.state is SponsorPositionState.PLANNED
    assert planned.actual_entry_availability is Availability.UNAVAILABLE
    assert active.state is SponsorPositionState.ACTIVE
    assert active.actual_entry_price == Decimal("101")
    assert active.actual_quantity == Decimal("2")
    assert model.entry_price == candidate.entry_price


def test_live_quantity_cannot_exceed_explicit_risk_constraint() -> None:
    candidate, _, _, _, outcome = _entry_fixture()
    risk = _risk(candidate, RiskState.CONSTRAINED)
    lifecycle = _lifecycle(candidate, risk)
    model = activate_objective_model(candidate, risk, replace(outcome, risk_result_id=risk.risk_result_id))
    decision = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.LIVE, clock=_NOW)
    evidence = SponsorExecutionEvidence("SPONSOR-EXECUTION-1", Decimal("101"), Decimal("11"), _NOW)
    with pytest.raises(ValueError, match="EXCEEDS_RISK_CONSTRAINT"):
        create_sponsor_position(decision, candidate, risk, model, actual_evidence=evidence)


def test_ignore_has_no_sponsor_position_branch() -> None:
    candidate, risk, lifecycle, _, _, model = _model_fixture()
    ignored = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.IGNORE, clock=_NOW)
    with pytest.raises(ValueError, match="NOT_APPLICABLE"):
        create_sponsor_position(ignored, candidate, risk, model)


def test_domain_009_events_publish_only_authoritative_outcomes() -> None:
    candidate, _, lifecycle, registry, outcome, model = _model_fixture()
    entry_event = publish_lifecycle_event(outcome, canonical_instrument=candidate.canonical_instrument, product=candidate.product, clock=_NOW)
    stop = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.STOP_LEVEL_CROSSED, "94", 3)
    closed = evaluate_objective_model(model, (stop,))
    close_event = publish_lifecycle_event(closed, canonical_instrument=candidate.canonical_instrument, product=candidate.product, clock=_NOW)
    assert entry_event.event_type is LifecycleEventType.ENTRY_TRIGGERED
    assert close_event.event_type is LifecycleEventType.MODEL_TRADE_CLOSED
    assert entry_event.event_id != outcome.entry_outcome_id
    with pytest.raises(ValueError, match="SOURCE_NOT_AUTHORITATIVE"):
        publish_lifecycle_event(model, canonical_instrument=candidate.canonical_instrument, product=candidate.product)


def test_live_model_closure_publishes_action_without_closing_sponsor_position() -> None:
    candidate, risk, lifecycle, registry, _, model = _model_fixture()
    decision = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.LIVE, clock=_NOW)
    evidence = SponsorExecutionEvidence("SPONSOR-EXECUTION-1", Decimal("101"), Decimal("2"), _NOW)
    position = create_sponsor_position(decision, candidate, risk, model, actual_evidence=evidence)
    stop = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.STOP_LEVEL_CROSSED, "94", 3)
    closed = evaluate_objective_model(model, (stop,))
    event = publish_live_action_required(closed, position, clock=_NOW)
    assert event.event_type is LifecycleEventType.LIVE_ACTION_REQUIRED
    assert position.state is SponsorPositionState.ACTIVE
    assert not hasattr(event, "broker_order")


def test_paper_position_closure_projects_without_actual_accounting() -> None:
    candidate, risk, lifecycle, registry, _, model = _model_fixture()
    decision = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.PAPER, clock=_NOW)
    position = create_sponsor_position(decision, candidate, risk, model)
    target = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.TARGET_LEVEL_CROSSED, "115", 3)
    closed_model = evaluate_objective_model(model, (target,))
    closed_position = project_paper_position_closure(position, closed_model)
    assert closed_position.state is SponsorPositionState.CLOSED
    assert closed_position.actual_exit_availability is Availability.UNAVAILABLE
    assert closed_position.actual_pnl_availability is Availability.UNAVAILABLE


def test_local_store_retains_and_verifies_every_contract_family(tmp_path) -> None:  # type: ignore[no-untyped-def]
    candidate, risk, lifecycle, registry, outcome, model = _model_fixture()
    judgment = _judgment(candidate)
    decision = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.PAPER, clock=_NOW)
    position = create_sponsor_position(decision, candidate, risk, model)
    observation = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.DATA_UNAVAILABLE, None, 3)
    event = publish_lifecycle_event(observation, canonical_instrument=candidate.canonical_instrument, product=candidate.product, clock=_NOW)
    store = LocalStep32Store(tmp_path / "step32")
    records = (candidate, judgment, risk, lifecycle, decision, outcome, model, position, observation, event)
    for record in records:
        path = store.retain(record)
        loaded = store.load(type(record).__name__, path.stem)
        assert loaded.record_type == type(record).__name__
        assert len(loaded.digest) == 64


def test_local_store_detects_tampering(tmp_path) -> None:  # type: ignore[no-untyped-def]
    candidate = _candidate()
    store = LocalStep32Store(tmp_path / "step32")
    path = store.retain(candidate)
    envelope = json.loads(path.read_text())
    envelope["payload"]["direction"] = "SHORT"
    path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="STORED_INTEGRITY_INVALID"):
        store.load(type(candidate).__name__, candidate.candidate_id)


def test_restart_replay_matches_or_requires_reconciliation() -> None:
    candidate, risk, lifecycle, registry, outcome, model = _model_fixture()
    target = _model_observation(model, candidate, lifecycle, registry, MonitoringSubmissionType.TARGET_LEVEL_CROSSED, "115", 3)
    projection = evaluate_objective_model(model, (target,))
    recovered = recover_objective_model(candidate, risk, outcome, (target,), projection)
    mismatch = recover_objective_model(candidate, risk, outcome, (target,), replace(projection, updated_at=projection.updated_at + timedelta(seconds=1)))
    assert recovered.state is RecoveryState.RECOVERED
    assert mismatch.state is RecoveryState.RECONCILIATION_REQUIRED
    assert mismatch.reconstructed_model.state is ObjectiveModelState.RECONCILIATION_REQUIRED


@pytest.mark.parametrize(
    "terminal",
    (
        CandidateLifecycleState.STALE,
        CandidateLifecycleState.PRE_ENTRY_INVALIDATED,
        CandidateLifecycleState.RISK_REJECTED,
        CandidateLifecycleState.RECONCILIATION_REQUIRED_PRE_ENTRY,
    ),
)
def test_pre_entry_terminal_states_are_explicit_and_fail_closed(terminal) -> None:  # type: ignore[no-untyped-def]
    lifecycle = _lifecycle()
    transitioned = transition_candidate_lifecycle(
        lifecycle,
        terminal,
        reason=terminal.value,
        clock=_NOW,
    )
    assert transitioned.state is terminal


def test_expired_risk_cannot_trigger_entry() -> None:
    candidate = _candidate()
    risk = record_risk_result(
        candidate,
        _judgment(candidate),
        RiskState.APPROVED,
        reason="RISK_APPROVED",
        clock=_NOW,
        valid_until=_NOW + timedelta(minutes=1),
    )
    lifecycle = _lifecycle(candidate, risk)
    registry = MonitoringAdmissionRegistry()
    previous = registry.admit(_submission(candidate, lifecycle, "99", 1), _context(candidate, lifecycle))
    current = registry.admit(_submission(candidate, lifecycle, str(candidate.entry_price), 2), _context(candidate, lifecycle))
    with pytest.raises(ValueError, match="ENTRY_TIMING_NOT_PERMITTED"):
        evaluate_entry_timing(candidate, risk, lifecycle, previous, current, clock=_NOW + timedelta(minutes=3))


def test_wrong_provider_or_inactive_monitoring_binding_is_rejected() -> None:
    candidate = _candidate()
    lifecycle = _lifecycle(candidate)
    submission = _submission(candidate, lifecycle, "99", 1)
    with pytest.raises(ValueError, match="BINDING_REJECTED"):
        MonitoringAdmissionRegistry().admit(
            submission,
            replace(_context(candidate, lifecycle), provider_source="OTHER_PROVIDER"),
        )
    with pytest.raises(ValueError, match="BINDING_REJECTED"):
        MonitoringAdmissionRegistry().admit(
            submission,
            replace(_context(candidate, lifecycle), binding_active=False),
        )


def test_post_entry_wrong_model_binding_is_rejected() -> None:
    candidate, _, lifecycle, _, _, model = _model_fixture()
    submission = _submission(
        candidate,
        lifecycle,
        "94",
        3,
        model_trade_id="MODEL-TRADE-WRONG",
        submission_type=MonitoringSubmissionType.STOP_LEVEL_CROSSED,
    )
    with pytest.raises(ValueError, match="BINDING_REJECTED"):
        MonitoringAdmissionRegistry().admit(
            submission,
            _context(candidate, lifecycle, model_trade_id=model.model_trade_id),
        )


def test_data_unavailable_remains_fact_and_event_not_market_conclusion() -> None:
    candidate, _, lifecycle, registry, _, model = _model_fixture()
    observation = _model_observation(
        model,
        candidate,
        lifecycle,
        registry,
        MonitoringSubmissionType.DATA_UNAVAILABLE,
        None,
        3,
    )
    event = publish_lifecycle_event(
        observation,
        canonical_instrument=candidate.canonical_instrument,
        product=candidate.product,
        clock=_NOW,
    )
    assert observation.observation_type is MonitoringSubmissionType.DATA_UNAVAILABLE
    assert event.event_type is LifecycleEventType.DATA_UNAVAILABLE
    assert not hasattr(observation, "close_reason")
    assert not hasattr(event, "exit_price")


def test_post_entry_session_gap_through_stop_closes_without_fill_claim() -> None:
    candidate, _, lifecycle, registry, _, model = _model_fixture()
    stop = _model_observation(
        model,
        candidate,
        lifecycle,
        registry,
        MonitoringSubmissionType.STOP_LEVEL_CROSSED,
        "93.50",
        3,
        session_continuous=False,
    )
    closed = evaluate_objective_model(model, (stop,))
    assert closed.close_reason is ModelCloseReason.STOP
    assert closed.exit_price == Decimal("93.50")
    assert not hasattr(closed, "fill_price")


def test_post_entry_missing_interval_requires_reconciliation() -> None:
    candidate, _, lifecycle, registry, _, model = _model_fixture()
    stop = _model_observation(
        model,
        candidate,
        lifecycle,
        registry,
        MonitoringSubmissionType.STOP_LEVEL_CROSSED,
        "93.50",
        3,
        previous_interval_available=False,
    )
    assert evaluate_objective_model(model, (stop,)).state is ObjectiveModelState.RECONCILIATION_REQUIRED


def test_step32_public_surface_has_no_order_or_public_ingress_authority() -> None:
    import kronos.swing.v1.step32 as step32

    public = set(step32.__all__)
    assert not public.intersection(
        {
            "place_order",
            "modify_order",
            "cancel_order",
            "start_public_server",
            "webhook_listener",
            "publish_pine_decision",
        }
    )
