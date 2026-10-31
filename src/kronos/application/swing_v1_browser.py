"""Sponsor-operable Browser projection for canonical Swing V1 Step 31/32 state."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from threading import RLock

from kronos.application.swing_v1_production import ProductionLifecycleResult
from kronos.application.swing_v1_review import (
    Step31EligibilityHandoff,
    Step31EligibleInstrument,
    SwingV1ReviewWorkflow,
)
from kronos.instrument import publish_instrument_context
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)
from kronos.swing.v1.step32 import (
    BusinessJudgment,
    CandidateLifecycle,
    LocalStep32Store,
    MonitoringObservation,
    MonitoringAdmissionContext,
    MonitoringAdmissionRegistry,
    MonitoringSubmissionType,
    EntryOutcome,
    EntryOutcomeState,
    ObjectiveModelState,
    ObjectiveModelTrade,
    RiskApproval,
    SponsorDecision,
    SponsorDecisionMode,
    SponsorPosition,
    SponsorPositionState,
    activate_objective_model,
    build_monitoring_submission,
    create_sponsor_position,
    evaluate_entry_timing,
    evaluate_objective_model,
    freeze_sponsor_decision,
    project_paper_position_closure,
    record_sponsor_decision,
)
from kronos.swing.v1.trade_construction import SwingV1TradeCandidate


Step31ProductionResolver = Callable[
    [Step31EligibilityHandoff, Step31EligibleInstrument],
    ProductionLifecycleResult,
]


@dataclass(frozen=True, slots=True)
class BrowserCandidateRecord:
    """Bound projection only; canonical domain records remain authoritative."""

    candidate: SwingV1TradeCandidate
    business_judgment: BusinessJudgment | None = None
    risk: RiskApproval | None = None
    lifecycle: CandidateLifecycle | None = None
    sponsor_decision: SponsorDecision | None = None
    objective_model: ObjectiveModelTrade | None = None
    sponsor_position: SponsorPosition | None = None
    monitoring_state: MonitoringConnectionState = (
        MonitoringConnectionState.DISCONNECTED
    )
    entry_outcome: EntryOutcome | None = None
    readiness_state: str = ""
    readiness_reason: str = ""
    monitoring_reason: str = ""

    def __post_init__(self) -> None:
        candidate_id = self.candidate.candidate_id
        bound = (
            self.business_judgment,
            self.risk,
            self.lifecycle,
            self.sponsor_decision,
            self.entry_outcome,
            self.objective_model,
            self.sponsor_position,
        )
        if (
            any(
                item is not None
                and getattr(item, "candidate_id", None) != candidate_id
                for item in bound
            )
            or type(self.monitoring_state) is not MonitoringConnectionState
            or any(
                type(value) is not str
                for value in (
                    self.readiness_state,
                    self.readiness_reason,
                    self.monitoring_reason,
                )
            )
            or (
                self.risk is not None
                and self.lifecycle is not None
                and self.lifecycle.risk_result_id != self.risk.risk_result_id
            )
            or (
                self.sponsor_decision is not None
                and self.risk is not None
                and self.sponsor_decision.risk_result_id
                != self.risk.risk_result_id
            )
            or (
                self.sponsor_position is not None
                and self.objective_model is not None
                and self.sponsor_position.model_trade_id
                != self.objective_model.model_trade_id
            )
        ):
            raise ValueError("BROWSER_STEP32_RECORD_BINDING_INVALID")

    @property
    def action_required(self) -> bool:
        return (
            self.objective_model is not None
            and self.objective_model.state is ObjectiveModelState.CLOSED
            and self.sponsor_decision is not None
            and self.sponsor_decision.mode is SponsorDecisionMode.LIVE
            and (
                self.sponsor_position is None
                or self.sponsor_position.state is not SponsorPositionState.CLOSED
            )
        )

    @property
    def browser_key(self) -> str:
        """Opaque route key; canonical contract identities stay off the UI."""

        return sha256(self.candidate.candidate_id.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class BrowserStep32Snapshot:
    swing_analysis_run_identity: str | None
    records: tuple[BrowserCandidateRecord, ...]
    synchronization_failure: str = ""

    def __post_init__(self) -> None:
        if (
            type(self.records) is not tuple
            or len({item.candidate.candidate_id for item in self.records})
            != len(self.records)
            or self.synchronization_failure not in {
                "",
                "TRADE_CANDIDATE_SOURCE_UNAVAILABLE",
                "TRADE_CANDIDATE_PRODUCTION_FAILED",
            }
        ):
            raise ValueError("BROWSER_STEP32_SNAPSHOT_INVALID")

    def record(self, candidate_id: str) -> BrowserCandidateRecord | None:
        return next(
            (item for item in self.records if item.candidate.candidate_id == candidate_id),
            None,
        )

    def record_for_browser_key(self, browser_key: str) -> BrowserCandidateRecord | None:
        return next(
            (item for item in self.records if item.browser_key == browser_key),
            None,
        )

    @property
    def trade_candidates(self) -> tuple[BrowserCandidateRecord, ...]:
        return tuple(item for item in self.records if item.objective_model is None)

    @property
    def active(self) -> tuple[BrowserCandidateRecord, ...]:
        return tuple(
            item
            for item in self.records
            if item.objective_model is not None
            and item.objective_model.state is not ObjectiveModelState.CLOSED
        )

    @property
    def closed(self) -> tuple[BrowserCandidateRecord, ...]:
        return tuple(
            item
            for item in self.records
            if item.objective_model is not None
            and item.objective_model.state is ObjectiveModelState.CLOSED
        )


class SwingV1BrowserOperationalization:
    """Application orchestration over existing Step-31/32 authorities."""

    def __init__(
        self,
        *,
        production_resolver: Step31ProductionResolver | None = None,
        step32_store: LocalStep32Store | None = None,
        recovered_records: Iterable[BrowserCandidateRecord] = (),
    ) -> None:
        records = tuple(recovered_records)
        if any(type(item) is not BrowserCandidateRecord for item in records):
            raise TypeError("BROWSER_STEP32_DEPENDENCY_INVALID")
        self._resolver = production_resolver
        self._store = step32_store
        self._lock = RLock()
        self._run_identity: str | None = None
        self._records = {
            item.candidate.candidate_id: item for item in records
        }
        self._retained_record_keys: set[tuple[str, str]] = set()
        self._failure = ""
        self._monitoring: dict[str, _CandidateMonitoringConsumer] = {}

    def snapshot(self) -> BrowserStep32Snapshot:
        with self._lock:
            records = tuple(sorted(
                self._records.values(),
                key=lambda item: (
                    item.candidate.construction_timestamp,
                    item.candidate.canonical_instrument,
                    item.candidate.candidate_id,
                ),
                reverse=True,
            ))
            return BrowserStep32Snapshot(
                self._run_identity,
                records,
                self._failure,
            )

    def synchronize_review(
        self,
        review: SwingV1ReviewWorkflow,
    ) -> BrowserStep32Snapshot:
        """Consume the canonical handoff; never manufacture missing eligibility."""

        if type(review) is not SwingV1ReviewWorkflow:
            raise TypeError("BROWSER_STEP32_REVIEW_INVALID")
        try:
            handoff = review.step31_eligibility_handoff()
        except ValueError as error:
            if str(error) != "V1_STEP31_HANDOFF_RUN_UNAVAILABLE":
                raise
            return self.snapshot()
        with self._lock:
            self._run_identity = handoff.swing_analysis_run_identity
            self._failure = ""
        if not handoff.eligible_instruments:
            return self.snapshot()
        if self._resolver is None:
            with self._lock:
                self._failure = "TRADE_CANDIDATE_SOURCE_UNAVAILABLE"
            return self.snapshot()
        produced: list[ProductionLifecycleResult] = []
        try:
            for eligibility in handoff.eligible_instruments:
                produced.append(self._resolver(handoff, eligibility))
        except Exception:
            with self._lock:
                self._failure = "TRADE_CANDIDATE_PRODUCTION_FAILED"
            return self.snapshot()
        for result, eligibility in zip(
            produced,
            handoff.eligible_instruments,
            strict=True,
        ):
            self.publish_production_result(result, eligibility=eligibility)
        return self.snapshot()

    def publish_production_result(
        self,
        result: ProductionLifecycleResult,
        *,
        eligibility: Step31EligibleInstrument | None = None,
    ) -> BrowserCandidateRecord:
        if type(result) is not ProductionLifecycleResult:
            raise TypeError("BROWSER_STEP32_PRODUCTION_RESULT_INVALID")
        record = BrowserCandidateRecord(
            result.candidate,
            result.business_judgment,
            result.risk,
            result.lifecycle,
            readiness_state=(
                ""
                if eligibility is None
                else eligibility.readiness_state.value.replace("_", " ")
            ),
            readiness_reason=(
                "" if eligibility is None else eligibility.readiness_reason
            ),
        )
        return self.publish(record)

    def publish(self, record: BrowserCandidateRecord) -> BrowserCandidateRecord:
        """Publish canonical records supplied by their owning components."""

        if type(record) is not BrowserCandidateRecord:
            raise TypeError("BROWSER_STEP32_RECORD_INVALID")
        if self._store is not None:
            for item in (
                record.business_judgment,
                record.risk,
                record.lifecycle,
                record.sponsor_decision,
                record.entry_outcome,
                record.objective_model,
                record.sponsor_position,
            ):
                key = _step32_record_key(item) if item is not None else None
                if item is not None and key not in self._retained_record_keys:
                    self._store.retain(item)
                    assert key is not None
                    self._retained_record_keys.add(key)
        with self._lock:
            self._records[record.candidate.candidate_id] = record
        return record

    def attach_candidate_monitoring(
        self,
        browser_key: str,
        capability: object,
        instrument: InstrumentRecord,
    ) -> None:
        """Bind one governed candidate to its Provider-private Kite session."""

        current = self._record_for_key(browser_key)
        if (
            getattr(capability, "active", False) is not True
            or type(instrument) is not InstrumentRecord
            or current.risk is None
            or not current.risk.permits_entry
            or current.lifecycle is None
        ):
            raise ValueError("BROWSER_CANDIDATE_MONITORING_NOT_PERMITTED")
        context = publish_instrument_context(
            current.candidate.canonical_instrument,
            current.candidate.product,
            instrument,
        )
        execution_context_identity = current.candidate.execution_context_identity
        if (
            execution_context_identity != context.identity
            and not execution_context_identity.startswith(f"{context.identity}|")
        ):
            raise ValueError("BROWSER_CANDIDATE_INSTRUMENT_BINDING_INVALID")
        consumer = _CandidateMonitoringConsumer(self, browser_key, instrument)
        session = capability.open_monitoring_session(consumer)
        consumer.bind_session(session)
        with self._lock:
            if current.candidate.candidate_id in self._monitoring:
                raise ValueError("BROWSER_CANDIDATE_MONITORING_ALREADY_ACTIVE")
            self._monitoring[current.candidate.candidate_id] = consumer
        try:
            session.subscribe((instrument,))
            session.connect()
        except Exception:
            consumer.close()
            self._mark_monitoring(
                browser_key,
                MonitoringConnectionState.CONTEXT_INCOMPLETE,
                "MONITORING_UNAVAILABLE",
            )
            raise ValueError("BROWSER_CANDIDATE_MONITORING_FAILED") from None

    def detach_candidate_monitoring(self, browser_key: str) -> None:
        current = self._record_for_key(browser_key)
        with self._lock:
            consumer = self._monitoring.pop(current.candidate.candidate_id, None)
        if consumer is not None:
            consumer.close()
        self._mark_monitoring(
            browser_key,
            MonitoringConnectionState.DISCONNECTED,
            "",
        )

    def close(self) -> None:
        """Release owned monitoring sessions without changing lifecycle records."""

        with self._lock:
            consumers = tuple(self._monitoring.values())
            self._monitoring.clear()
        for consumer in consumers:
            consumer.close(preserve_state=True)

    def record_sponsor_choice(
        self,
        browser_key: str,
        mode: SponsorDecisionMode,
    ) -> SponsorDecision:
        if type(mode) is not SponsorDecisionMode:
            raise ValueError("BROWSER_SPONSOR_DECISION_INVALID")
        with self._lock:
            current = next(
                (
                    item
                    for item in self._records.values()
                    if item.browser_key == browser_key
                ),
                None,
            )
        if (
            current is None
            or current.risk is None
            or not current.risk.permits_entry
            or current.lifecycle is None
        ):
            raise ValueError("BROWSER_SPONSOR_DECISION_NOT_PERMITTED")
        decision = record_sponsor_decision(
            current.candidate,
            current.risk,
            current.lifecycle,
            mode,
            previous=current.sponsor_decision,
        )
        updated = replace(current, sponsor_decision=decision)
        self.publish(updated)
        return decision

    def apply_entry_observations(
        self,
        browser_key: str,
        previous: MonitoringObservation | None,
        current: MonitoringObservation,
    ) -> EntryOutcome:
        """Apply governed DOMAIN-002 facts through existing KR-380 authority."""

        current_record = self._record_for_key(browser_key)
        if current_record.risk is None or current_record.lifecycle is None:
            raise ValueError("BROWSER_ENTRY_MONITORING_NOT_PERMITTED")
        outcome = evaluate_entry_timing(
            current_record.candidate,
            current_record.risk,
            current_record.lifecycle,
            previous,
            current,
        )
        changes: dict[str, object] = {"entry_outcome": outcome}
        if outcome.state is EntryOutcomeState.ENTRY_TRIGGERED:
            model = activate_objective_model(
                current_record.candidate,
                current_record.risk,
                outcome,
            )
            changes["objective_model"] = model
            decision = current_record.sponsor_decision
            if decision is not None:
                decision = freeze_sponsor_decision(decision)
                changes["sponsor_decision"] = decision
                if decision.mode in {
                    SponsorDecisionMode.LIVE,
                    SponsorDecisionMode.PAPER,
                }:
                    changes["sponsor_position"] = create_sponsor_position(
                        decision,
                        current_record.candidate,
                        current_record.risk,
                        model,
                    )
        self.publish(replace(current_record, **changes))
        return outcome

    def apply_model_observations(
        self,
        browser_key: str,
        observations: tuple[MonitoringObservation, ...],
        *,
        irrecoverable_ambiguity: bool = False,
    ) -> ObjectiveModelTrade:
        """Apply governed observations through existing KR-390 authority."""

        current_record = self._record_for_key(browser_key)
        if current_record.objective_model is None:
            raise ValueError("BROWSER_MODEL_MONITORING_NOT_ACTIVE")
        model = evaluate_objective_model(
            current_record.objective_model,
            observations,
            irrecoverable_ambiguity=irrecoverable_ambiguity,
        )
        position = current_record.sponsor_position
        if (
            model.state is ObjectiveModelState.CLOSED
            and position is not None
            and position.mode is SponsorDecisionMode.PAPER
        ):
            position = project_paper_position_closure(position, model)
        self.publish(replace(
            current_record,
            objective_model=model,
            sponsor_position=position,
        ))
        return model

    def _record_for_key(self, browser_key: str) -> BrowserCandidateRecord:
        with self._lock:
            current = next(
                (
                    item
                    for item in self._records.values()
                    if item.browser_key == browser_key
                ),
                None,
            )
        if current is None:
            raise ValueError("BROWSER_TRADE_CANDIDATE_NOT_FOUND")
        return current

    def _retain_observation(self, observation: MonitoringObservation) -> None:
        if self._store is None:
            return
        key = _step32_record_key(observation)
        if key not in self._retained_record_keys:
            self._store.retain(observation)
            self._retained_record_keys.add(key)

    def _mark_monitoring(
        self,
        browser_key: str,
        state: MonitoringConnectionState,
        reason: str,
    ) -> None:
        current = self._record_for_key(browser_key)
        self.publish(replace(
            current,
            monitoring_state=state,
            monitoring_reason=reason,
        ))


class _CandidateMonitoringConsumer:
    """Translate normalized Kite facts into the existing DOMAIN-002 path."""

    def __init__(
        self,
        workflow: SwingV1BrowserOperationalization,
        browser_key: str,
        instrument: InstrumentRecord,
    ) -> None:
        self._workflow = workflow
        self._browser_key = browser_key
        self._instrument = instrument
        self._registry = MonitoringAdmissionRegistry()
        self._previous_entry: MonitoringObservation | None = None
        self._session: object | None = None
        self._closed = False

    def bind_session(self, session: object) -> None:
        self._session = session

    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        if self._closed:
            return
        try:
            if type(tick) is not ProviderMarketTick or tick.instrument != self._instrument:
                raise ValueError("INSTRUMENT_BINDING_MISMATCH")
            record = self._workflow._record_for_key(self._browser_key)
            lifecycle = record.lifecycle
            if lifecycle is None:
                raise ValueError("MONITORING_BINDING_UNAVAILABLE")
            submission_type = _submission_type(record, tick)
            model_id = (
                None
                if record.objective_model is None
                else record.objective_model.model_trade_id
            )
            submission = build_monitoring_submission(
                tick,
                submission_id="MONITORING-" + sha256("|".join((
                    record.candidate.candidate_id,
                    tick.connection_id,
                    tick.observed_at.isoformat(),
                    str(tick.source_sequence),
                    submission_type.value,
                )).encode()).hexdigest(),
                candidate_id=record.candidate.candidate_id,
                monitoring_binding_id=lifecycle.monitoring_binding_id,
                model_trade_id=model_id,
                product=record.candidate.product,
                direction=record.candidate.direction,
                submission_type=submission_type,
                reference="CANDIDATE-LIFECYCLE-MONITORING",
                boundary=tick.observed_at,
                timeframe="TICK",
                session_identity=tick.connection_id,
                canonical_instrument=record.candidate.canonical_instrument,
            )
            context = MonitoringAdmissionContext(
                record.candidate.candidate_id,
                lifecycle.monitoring_binding_id,
                model_id,
                record.candidate.canonical_instrument,
                f"{self._instrument.exchange}:{self._instrument.trading_symbol}",
                record.candidate.product,
                record.candidate.direction,
                tick.source,
                tick.connection_id,
                True,
                tick.observed_at,
                "TICK",
                tick.connection_id,
            )
            observation = self._registry.admit(
                submission,
                context,
                clock=datetime.now(UTC),
            )
            self._workflow._retain_observation(observation)
            if record.objective_model is None:
                self._workflow.apply_entry_observations(
                    self._browser_key,
                    self._previous_entry,
                    observation,
                )
                self._previous_entry = observation
            else:
                model = self._workflow.apply_model_observations(
                    self._browser_key,
                    (observation,),
                )
                if model.state is ObjectiveModelState.CLOSED:
                    self.close()
        except Exception:
            self._workflow._mark_monitoring(
                self._browser_key,
                MonitoringConnectionState.CONTEXT_INCOMPLETE,
                "REVIEW_REQUIRED_DATA_GAP",
            )

    def on_order_update(self, _update: ProviderOrderUpdateEvidence) -> None:
        """Order evidence never enters objective-model monitoring."""

    def on_connection_state(self, state: MonitoringConnectionState) -> None:
        if self._closed:
            return
        reason = (
            "REVIEW_REQUIRED_DATA_GAP"
            if state in {
                MonitoringConnectionState.RECONNECTING,
                MonitoringConnectionState.CONTEXT_INCOMPLETE,
            }
            else ""
        )
        self._workflow._mark_monitoring(self._browser_key, state, reason)

    def close(self, *, preserve_state: bool = False) -> None:
        if self._closed or self._session is None:
            return
        self._closed = True
        try:
            self._session.unsubscribe((self._instrument,))  # type: ignore[attr-defined]
        finally:
            self._session.disconnect()  # type: ignore[attr-defined]
            if not preserve_state:
                self._workflow._mark_monitoring(
                    self._browser_key,
                    MonitoringConnectionState.DISCONNECTED,
                    "",
                )


def _submission_type(
    record: BrowserCandidateRecord,
    tick: ProviderMarketTick,
) -> MonitoringSubmissionType:
    if record.objective_model is None:
        return MonitoringSubmissionType.ENTRY_LEVEL_CROSSED
    model = record.objective_model
    if model.direction == "LONG":
        if tick.last_price <= model.stop_price:
            return MonitoringSubmissionType.STOP_LEVEL_CROSSED
        if tick.last_price >= model.target_price:
            return MonitoringSubmissionType.TARGET_LEVEL_CROSSED
    else:
        if tick.last_price >= model.stop_price:
            return MonitoringSubmissionType.STOP_LEVEL_CROSSED
        if tick.last_price <= model.target_price:
            return MonitoringSubmissionType.TARGET_LEVEL_CROSSED
    return MonitoringSubmissionType.FACTUAL_MARKET_TICK


def _step32_record_key(record: object) -> tuple[str, str]:
    identity_fields = {
        BusinessJudgment: "business_judgment_id",
        RiskApproval: "risk_result_id",
        CandidateLifecycle: "candidate_id",
        SponsorDecision: "sponsor_decision_id",
        EntryOutcome: "entry_outcome_id",
        MonitoringObservation: "observation_id",
        ObjectiveModelTrade: "model_trade_id",
        SponsorPosition: "sponsor_position_id",
    }
    field = identity_fields.get(type(record))
    record_id = getattr(record, field, None) if field is not None else None
    if record_id is None:
        raise ValueError("BROWSER_STEP32_RECORD_ID_UNAVAILABLE")
    return type(record).__name__, record_id


__all__ = [
    "BrowserCandidateRecord",
    "BrowserStep32Snapshot",
    "Step31ProductionResolver",
    "SwingV1BrowserOperationalization",
]
