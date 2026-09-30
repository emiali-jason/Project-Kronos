"""Exact-contract MCX V1 record owner; no broker execution capability.

This owner is inert unless a governed Browser composition installs it. The
published Browser default continues to reject every MCX Step-31 mutation.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from threading import RLock
from typing import Callable
from zoneinfo import ZoneInfo

from kronos.application.swing_mcx_integrated import SwingMcxIntegratedWorkflow
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_visual_v3_live import NativeReviewIntakeWorkflow
from kronos.common.maintenance_admission import (
    AdmissionTicket, MaintenanceAdmissionCoordinator,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalDataError
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState, MonitoringSubscriptionEvidence, ProviderMarketTick,
)
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from kronos.provider.kite.marketdata.kite_market_data_provider import KiteMarketDataProvider
from kronos.swing.v1.mcx_broker_fill_evidence import LocalMcxBrokerFillEvidenceStore
from kronos.swing.v1.mcx_contract_lifecycle import (
    LocalMcxHistoricalContractStore, McxContractBoundLifecycle,
)
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_contract_selection import McxSelectionRole
from kronos.swing.v1.mcx_kr380_issuer import McxKr380Rejected
from kronos.swing.v1.mcx_live_attestation import (
    LocalMcxLiveFillAttestationStore, McxLiveFillAttestation,
)
from kronos.swing.v1.mcx_trade_plan import LocalMcxTradePlanStore, McxTradePlanRecord
from kronos.swing.v1.mcx_v1_production_issuer import issue_v1_production_signal
from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleState, ActiveTradeLifecycleService, TradeExitReason,
)
from kronos.swing.v1.mcx_v1_advisory import LocalMcxV1AdvisoryStore
from kronos.swing.v1.native_sponsor_decision import (
    LocalSponsorDecisionStore, create_trade_plan_business_judgment,
    record_trade_plan_risk_result,
)
from kronos.swing.v1.step32 import RiskState


_IST = ZoneInfo("Asia/Kolkata")
_MCX_ADVISORY_WORKERS = 2
_MCX_ADVISORY_PENDING_LIMIT = 5
_MCX_ADVISORY_ATTEMPT_LIMIT = 32


class _BoundedMcxAdvisoryWorker:
    """Bounded, deduplicated historical acquisition outside tick dispatch."""

    def __init__(self, *, maximum_workers: int = _MCX_ADVISORY_WORKERS,
                 maximum_pending: int = _MCX_ADVISORY_PENDING_LIMIT) -> None:
        if (type(maximum_workers) is not int or maximum_workers < 2
                or type(maximum_pending) is not int
                or maximum_pending < maximum_workers):
            raise ValueError("MCX_V1_ADVISORY_WORKER_LIMIT_INVALID")
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=maximum_workers, thread_name_prefix="kronos-mcx-advisory")
        self._maximum_pending = maximum_pending
        self._pending: dict[str, Future[object]] = {}
        self._attempted: OrderedDict[str, str] = OrderedDict()
        self._failures: dict[str, str] = {}
        self._closed = False

    def submit(self, identity: str, request_identity: str,
               work: Callable[[], object],
               ticket: AdmissionTicket | None = None) -> bool:
        if not identity or not request_identity or not callable(work):
            raise ValueError("MCX_V1_ADVISORY_WORK_INVALID")
        with self._lock:
            if (self._closed or identity in self._pending
                    or self._attempted.get(identity) == request_identity
                    or len(self._pending) >= self._maximum_pending):
                return False

            def owned_work() -> object:
                if ticket is None:
                    return work()
                with ticket.activate():
                    return work()

            try:
                future = self._executor.submit(owned_work)
            except RuntimeError:
                return False
            self._pending[identity] = future
            self._attempted[identity] = request_identity
            self._attempted.move_to_end(identity)
            while len(self._attempted) > _MCX_ADVISORY_ATTEMPT_LIMIT:
                removable = next((key for key in self._attempted
                                  if key not in self._pending), None)
                if removable is None:
                    break
                del self._attempted[removable]
                self._failures.pop(removable, None)
        # An already-completed future invokes this callback synchronously.
        # Register outside the leaf lock, so final coordinator release never
        # occurs under either this caller's or the completion thread's lock.
        future.add_done_callback(
            lambda completed, key=identity: self._completed(key, completed, ticket))
        return True

    def _completed(self, identity: str, future: Future[object],
                   ticket: AdmissionTicket | None = None) -> None:
        try:
            error = None if future.cancelled() else future.exception()
            failure = ('CancelledError' if future.cancelled() else
                       type(error).__name__ if error is not None else None)
            with self._lock:
                if self._pending.get(identity) is future:
                    del self._pending[identity]
                if failure is None:
                    self._failures.pop(identity, None)
                else:
                    # Operational only: exception class, never payload text.
                    self._failures[identity] = failure
        finally:
            # Zero counted owners implies final writes AND pending bookkeeping
            # have finished. A canonical handoff cannot wake in between them.
            if ticket is not None:
                ticket.release()

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": "CLOSED" if self._closed else "AVAILABLE",
                "pending": len(self._pending),
                "maximum_pending": self._maximum_pending,
                "attempted": len(self._attempted),
                "maximum_attempted": _MCX_ADVISORY_ATTEMPT_LIMIT,
                "failures": dict(self._failures),
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        # Governed shutdown calls this only after counted work reaches zero.
        self._executor.shutdown(wait=True, cancel_futures=False)


class SwingMcxV1OperationalControl:
    """One trusted process owner for a selected run and its historical positions.

    Current-run fences apply to new admissions and PAPER activation. Existing
    positions keep their retained derivative for monitoring and factual exits.
    Neither the owner nor its dependencies have a broker order method.
    """

    def __init__(
        self, workflow: SwingMcxIntegratedWorkflow | None,
        review_owner: NativeReviewIntakeWorkflow | None,
        native_review: NativeReviewWorkflow,
        plans: LocalMcxTradePlanStore,
        sponsor: LocalSponsorDecisionStore, lifecycle: ActiveTradeLifecycleService,
        historical: LocalMcxHistoricalContractStore,
        outcomes: LocalMcxV1AdvisoryStore, master: ProviderInstrumentSnapshotStore,
        mtf: MtfFactEvidenceStore,
        provider: KiteMarketDataProvider | Callable[[], KiteMarketDataProvider],
        calendar: MarketCalendarPublisher,
        live_attestations: LocalMcxLiveFillAttestationStore,
        broker_evidence: LocalMcxBrokerFillEvidenceStore,
        capability: object | Callable[[], object],
    ) -> None:
        if ((workflow is not None and type(workflow) is not SwingMcxIntegratedWorkflow)
                or (review_owner is not None and type(review_owner) is not NativeReviewIntakeWorkflow)
                or (workflow is not None and review_owner is None)
                or type(native_review) is not NativeReviewWorkflow
                or (review_owner is not None and review_owner.native_review is not native_review)
                or type(plans) is not LocalMcxTradePlanStore
                or type(sponsor) is not LocalSponsorDecisionStore
                or type(lifecycle) is not ActiveTradeLifecycleService
                or type(historical) is not LocalMcxHistoricalContractStore
                or type(outcomes) is not LocalMcxV1AdvisoryStore
                or type(master) is not ProviderInstrumentSnapshotStore
                or type(mtf) is not MtfFactEvidenceStore
                or (type(provider) is not KiteMarketDataProvider
                    and not callable(provider))
                or type(calendar) is not MarketCalendarPublisher
                or type(live_attestations) is not LocalMcxLiveFillAttestationStore
                or type(broker_evidence) is not LocalMcxBrokerFillEvidenceStore
                or capability is None
                or native_review._active_lifecycle is not lifecycle
                or native_review._mcx_historical_contract_store is not historical):
            raise ValueError("MCX_V1_OPERATIONAL_OWNER_INVALID")
        self.workflow = workflow
        self.review_owner, self.native_review = review_owner, native_review
        self.plans, self.sponsor = plans, sponsor
        self.lifecycle, self.historical = lifecycle, historical
        self.outcomes, self.master, self.mtf = outcomes, master, mtf
        self._provider_source = (provider if callable(provider)
                                 else lambda: provider)
        self._capability_source = (capability if callable(capability)
                                   else lambda: capability)
        self.calendar = calendar
        self.live_attestations, self.broker_evidence = live_attestations, broker_evidence
        self._lock = RLock()
        self._maintenance_admission: MaintenanceAdmissionCoordinator | None = None
        self._advisory_worker = _BoundedMcxAdvisoryWorker()
        self.bound = McxContractBoundLifecycle(lifecycle, historical)
        native_review.bind_mcx_v1_tick_owner(self.on_paper_tick)

    def bind_workflow(self, workflow: SwingMcxIntegratedWorkflow,
                      review_owner: NativeReviewIntakeWorkflow) -> None:
        """Select the current run without replacing the historical owner/worker.

        No acquisition or reservation occurs here. Older queued completions
        retain their original byte fence and additionally fail _plan after a
        successor is selected. Historical exits never depend on this slot.
        """
        if (type(workflow) is not SwingMcxIntegratedWorkflow
                or type(review_owner) is not NativeReviewIntakeWorkflow
                or review_owner.native_review is not self.native_review):
            raise ValueError("MCX_V1_OPERATIONAL_OWNER_INVALID")
        workflow._current()
        with self._lock:
            self.workflow, self.review_owner = workflow, review_owner

    def bind_maintenance_admission(
        self, admission: MaintenanceAdmissionCoordinator,
    ) -> None:
        if type(admission) is not MaintenanceAdmissionCoordinator:
            raise TypeError("MCX_V1_MAINTENANCE_ADMISSION_INVALID")
        with self._lock:
            if self._maintenance_admission is not None:
                raise ValueError("MCX_V1_MAINTENANCE_ADMISSION_CONFLICT")
            if self._advisory_worker.status()["pending"]:
                raise ValueError("MCX_V1_MAINTENANCE_ADMISSION_LATE")
            self._maintenance_admission = admission

    def worker_status(self) -> dict[str, object]:
        return self._advisory_worker.status()

    def close(self) -> None:
        self._advisory_worker.close()

    def _active_capability(self):
        capability = self._capability_source()
        if getattr(capability, "active", False) is not True:
            raise ValueError("MCX_V1_PROVIDER_CAPABILITY_UNAVAILABLE")
        return capability

    def _active_provider(self) -> KiteMarketDataProvider:
        provider = self._provider_source()
        if type(provider) is not KiteMarketDataProvider:
            raise ValueError("MCX_V1_PROVIDER_CAPABILITY_UNAVAILABLE")
        return provider

    def _plan(self, run: str, family: McxFamily, plan_id: str) -> McxTradePlanRecord:
        if (self.workflow is None or self.review_owner is None
                or run != self.workflow.run_identity or type(family) is not McxFamily
                or not plan_id.startswith("MCX-TRADE-PLAN-")
                or len(plan_id) != len("MCX-TRADE-PLAN-") + 64
                or any(char not in "0123456789abcdef" for char in plan_id[-64:])):
            raise ValueError("MCX_V1_PLAN_IDENTITY_INVALID")
        path = self.plans.root / run / family.value / (plan_id + ".json")
        plan = self.plans.load(path)
        if (plan.native_run_identity, plan.family, plan.trade_plan_id) != (
                run, family, plan_id):
            raise ValueError("MCX_V1_PLAN_IDENTITY_CHANGED")
        return plan

    def _selected(self, plan: McxTradePlanRecord) -> InstrumentRecord:
        selected = self.workflow.selections.load(plan.native_run_identity, plan.family)
        offer = self.workflow.offers[plan.family]
        fact = (offer.near if selected.role is McxSelectionRole.NEAR
                else offer.next_eligible)
        if (fact is None or selected.integrity_sha256 != plan.selection_sha256
                or (fact.instrument.trading_symbol,
                    fact.instrument.expiry.isoformat()) !=
                   (plan.contract_symbol, plan.expiry)):
            raise ValueError("MCX_V1_SELECTED_FUTURE_CHANGED")
        return fact.instrument

    @staticmethod
    def _decision_inputs(plan: McxTradePlanRecord):
        judgment = create_trade_plan_business_judgment(
            plan, validation_identity="MCX_V1_ADVISORY_EXACT_PLAN",
            created_at=plan.created_at)
        risk = record_trade_plan_risk_result(
            plan, judgment, RiskState.UNAVAILABLE,
            reason="MONETARY_MULTIPLIER_UNKNOWN", evaluated_at=plan.created_at)
        return judgment, risk

    def _current_plan_owner(self, plan: McxTradePlanRecord):
        instrument = self._selected(plan)
        _, owner = self.workflow._v1_current_plan_owner(
            self.review_owner, plan.family, instrument, plan, self.plans)
        return instrument, owner

    @staticmethod
    def _advisory_request_identity(
        plan: McxTradePlanRecord, schedule: object, evaluated_at: datetime,
    ) -> str | None:
        """Return one key per newly completed eligible hour range."""

        start = plan.observation_boundary - timedelta(hours=1)
        window = schedule.window_at(start)
        if (window is None or evaluated_at >= plan.entry_eligibility_boundary
                or schedule.window_at(plan.observation_boundary) != window):
            return None
        latest = min(evaluated_at, plan.entry_eligibility_boundary,
                     window.window_close)
        completed = int((latest - start) // timedelta(hours=1))
        if completed < 2:
            return None
        boundary = start + timedelta(hours=completed)
        return sha256("|".join((
            plan.trade_plan_id, plan.integrity_hash,
            schedule.session_identity, boundary.isoformat(),
        )).encode()).hexdigest()

    def on_paper_tick(self, position_id: str, tick: ProviderMarketTick,
                      connection: MonitoringConnectionState, *,
                      subscription_evidence: MonitoringSubscriptionEvidence | None = None,
                      current_subscription: Callable | None = None):
        """Use retained advice or queue one counted historical acquisition.

        The serial monitoring callback never performs historical I/O. Once a
        worker retains an exact-current advisory, only a later fresh CMP can
        activate PAPER; the tick which caused acquisition is never backfilled.
        """
        with self._lock:
            position = self.lifecycle._require(position_id)
            if (connection not in {MonitoringConnectionState.CONNECTED,
                                   MonitoringConnectionState.CONTEXT_INCOMPLETE}
                    or position.mcx_v1_contract_symbol is None
                    or position.state not in {
                        ActiveLifecycleState.PAPER_ARMED,
                        ActiveLifecycleState.MONITORING_UNAVAILABLE,
                    }):
                return None
            if (subscription_evidence is not None
                    or connection is MonitoringConnectionState.CONTEXT_INCOMPLETE):
                if (type(subscription_evidence) is not MonitoringSubscriptionEvidence
                        or subscription_evidence.state is not connection
                        or not subscription_evidence.admits(tick)
                        or not callable(current_subscription)
                        or current_subscription() != subscription_evidence):
                    return None
            family = McxFamily(position.canonical_instrument)
            if self.workflow is None or self.review_owner is None:
                # Historical armed positions have no current entry authority.
                # Active positions continue through the existing coordinator.
                return None
            try:
                plan = self._plan(self.workflow.run_identity, family,
                                  position.trade_plan_id)
                instrument, owner = self._current_plan_owner(plan)
            except (OSError, ValueError):
                # A historical armed plan has no current entry authority.
                # Keep it held without interrupting shared tick dispatch for
                # independently active positions or reusing a successor plan.
                return None
            if tick.instrument != instrument:
                raise ValueError("MCX_V1_TICK_CONTRACT_MISMATCH")
            schedule = self.calendar.schedule(
                "MCX", tick.observed_at.astimezone(_IST).date(),
                observed_at=tick.received_at)
            if schedule is None:
                return None
            outcome = self.outcomes.load_for_plan(plan.trade_plan_id)
            if outcome is not None:
                if tick.received_at <= outcome.confirmed_at:
                    # Confirmation is retained first. This tick cannot become a
                    # retrospective fill; wait for the next observed exact CMP.
                    return None
                return self.bound.activate_v1_paper_at_observed_cmp(
                    position_id, plan, outcome, tick, schedule,
                    plan_store=self.plans, sponsor_store=self.sponsor,
                    outcome_store=self.outcomes, connection_state=connection,
                    subscription_evidence=subscription_evidence,
                    current_subscription=current_subscription,
                    commit_guard=owner.final_fence,
                    current_readset=lambda: (
                        self._plan(plan.native_run_identity, family,
                                   plan.trade_plan_id),
                        self.outcomes.load_for_plan(plan.trade_plan_id), tick),
                )
            try:
                provider = self._active_provider()
            except ValueError:
                return None
            _, risk = self._decision_inputs(plan)
            admission = self._maintenance_admission
            request_identity = self._advisory_request_identity(
                plan, schedule, tick.received_at)
            if request_identity is None:
                return None

        # The coordinator lock is acquired only after the leaf application
        # lock is released. The active callback ticket permits this counted
        # child admission even when maintenance has just fenced new roots.
        ticket = (None if admission is None else
                  admission.admit("MONITORING_CALLBACK"))
        if admission is not None and ticket is None:
            return None

        def evaluate() -> object:
            try:
                return issue_v1_production_signal(
                    plan=plan, risk=risk, instrument=instrument,
                    master=self.master, provider=provider, mtf=self.mtf,
                    schedule=schedule, owner=owner,
                    current_plan=lambda: self._plan(
                        plan.native_run_identity, family, plan.trade_plan_id),
                    monitoring_binding_identity=position.position_id,
                    evaluated_at=tick.received_at, store=self.outcomes)
            except (McxKr380Rejected, HistoricalDataError):
                return None

        submitted = self._advisory_worker.submit(
            position.position_id, request_identity, evaluate, ticket)
        if not submitted and ticket is not None:
            ticket.release()
        return None

    def admit_paper(self, *, run: str, family: McxFamily, plan_id: str,
                    plan_sha256: str, decided_at: datetime):
        with self._lock:
            capability = self._active_capability()
            plan = self._plan(run, family, plan_id)
            if plan.integrity_hash != plan_sha256:
                raise ValueError("MCX_V1_PLAN_STALE")
            instrument = self._selected(plan)
            judgment, risk = self._decision_inputs(plan)
            result, position, binding = self.workflow.admit_v1_paper_position(
                self.review_owner, family, instrument, plan, self.plans,
                self.sponsor, self.lifecycle, self.historical,
                judgment, risk, decided_at=decided_at)
            if (result.position is None or position is None
                    or binding.instrument != instrument):
                raise ValueError("MCX_V1_PAPER_ADMISSION_INCOMPLETE")
        self.native_review.attach_lifecycle_monitoring(
            position.position_id, capability, instrument)
        return position

    def paper_exit(self, position_id: str, expected_hash: str):
        with self._lock:
            position = self.lifecycle._require(position_id)
            if (position.integrity_hash != expected_hash
                    or position.mcx_v1_contract_symbol is None):
                raise ValueError("MCX_V1_PAPER_EXIT_STALE")
            latest = self.native_review.latest_mcx_observation(position_id)
            if latest is None:
                raise ValueError("MCX_V1_FACTUAL_EXIT_CMP_UNAVAILABLE")
            tick, connection = latest
            if connection not in {MonitoringConnectionState.CONNECTED,
                                   MonitoringConnectionState.CONTEXT_INCOMPLETE}:
                raise ValueError("MCX_V1_FACTUAL_EXIT_CMP_UNAVAILABLE")
            schedule = self.calendar.schedule(
                "MCX", tick.observed_at.astimezone(_IST).date(),
                observed_at=tick.received_at)
            if schedule is None:
                raise ValueError("MCX_V1_FACTUAL_EXIT_SESSION_UNAVAILABLE")
            return self.bound.manual_paper_exit_at_cmp(position_id, tick, schedule)

    def admit_live(self, *, run: str, family: McxFamily, plan_id: str,
                   plan_sha256: str, attestation: McxLiveFillAttestation,
                   broker_bytes: bytes, decided_at: datetime):
        with self._lock:
            capability = self._active_capability()
            plan = self._plan(run, family, plan_id)
            if plan.integrity_hash != plan_sha256:
                raise ValueError("MCX_V1_PLAN_STALE")
            instrument = self._selected(plan)
            outcome = self.outcomes.load_for_plan(plan_id)
            if outcome is not None and outcome.confirmed_at >= attestation.fill_at:
                outcome = None
            judgment, risk = self._decision_inputs(plan)
            result, position, binding = self.workflow.admit_v1_manual_live_position(
                self.review_owner, family, instrument, plan, self.plans,
                self.sponsor, self.live_attestations, self.broker_evidence,
                broker_bytes, attestation, outcome, self.outcomes,
                self.lifecycle, self.historical, judgment, risk,
                decided_at=decided_at)
            if (result.position is None or position is None
                    or binding.instrument != instrument):
                raise ValueError("MCX_V1_LIVE_ADMISSION_INCOMPLETE")
        self.native_review.attach_lifecycle_monitoring(
            position.position_id, capability, instrument)
        return position

    def record_manual_live_entry(
        self, *, run: str, family: McxFamily, plan_id: str,
        plan_sha256: str, contract: str, expiry: str, lots: int,
        fill_price: Decimal, fill_at: datetime, evidence_id: str,
        evidence_sha256: str, evidence_bytes: bytes, attested_at: datetime,
    ):
        with self._lock:
            plan = self._plan(run, family, plan_id)
            outcome = self.outcomes.load_for_plan(plan_id)
            if outcome is not None and outcome.confirmed_at >= fill_at:
                outcome = None
            if (plan.integrity_hash != plan_sha256
                    or (contract, expiry) != (plan.contract_symbol, plan.expiry)
                    or type(lots) is not int or lots <= 0
                    or sha256(evidence_bytes).hexdigest() != evidence_sha256):
                raise ValueError("MCX_V1_LIVE_ENTRY_INPUT_STALE")
            retained_path = self.live_attestations._path(plan_id)
            if retained_path.is_symlink():
                raise ValueError("MCX_V1_LIVE_ENTRY_HISTORY_CHANGED")
            if retained_path.exists():
                attestation = self.live_attestations.load(plan_id)
                if (attestation.contract_symbol, attestation.expiry, attestation.lots,
                    attestation.fill_price, attestation.fill_at,
                    attestation.broker_evidence_id, attestation.broker_evidence_sha256) != (
                    contract, expiry, lots, fill_price, fill_at, evidence_id, evidence_sha256):
                    raise ValueError("MCX_V1_LIVE_ENTRY_REPLAY_CONFLICT")
                # Reuse the original attestation time; never rewrite evidence
                # merely because the same Browser request is retried later.
                attested_at = attestation.attested_at
            else:
                attestation = McxLiveFillAttestation.create(
                    plan, contract_symbol=contract, expiry=expiry, lots=lots,
                    provider_order_quantity=None, entry_outcome=outcome,
                    fill_price=fill_price, fill_at=fill_at,
                    broker_evidence_id=evidence_id,
                    broker_evidence_sha256=evidence_sha256,
                    attested_at=attested_at, v1_manual=True)
            return self.admit_live(
                run=run, family=family, plan_id=plan_id,
                plan_sha256=plan_sha256, attestation=attestation,
                broker_bytes=evidence_bytes, decided_at=attested_at)

    def live_exit(self, position_id: str, expected_hash: str,
                  attestation: McxLiveFillAttestation, broker_bytes: bytes,
                  reason: TradeExitReason):
        with self._lock:
            position = self.lifecycle._require(position_id)
            if (position.mcx_v1_contract_symbol is None
                    or (position.state is not ActiveLifecycleState.CLOSED
                        and position.integrity_hash != expected_hash)):
                raise ValueError("MCX_V1_LIVE_EXIT_STALE")
            return self.bound.record_live_exit(
                position_id, actual_exit=attestation.fill_price,
                exit_timestamp=attestation.fill_at, reason=reason,
                attestation=attestation,
                attestation_store=self.live_attestations,
                broker_store=self.broker_evidence,
                broker_bytes=broker_bytes)

    def record_manual_live_exit(
        self, *, position_id: str, expected_hash: str,
        contract: str, expiry: str, lots: int,
        fill_price: Decimal, fill_at: datetime, evidence_id: str,
        evidence_sha256: str, evidence_bytes: bytes, reason: TradeExitReason,
        attested_at: datetime,
    ):
        with self._lock:
            position = self.lifecycle._require(position_id)
            binding = self.historical.load(position_id)
            entry = self.live_attestations.load(position.trade_plan_id)
            outage_exit = (position.mode.value == "LIVE" and (
                position.state is ActiveLifecycleState.EVENT_UNRESOLVED
                or (position.state is ActiveLifecycleState.MONITORING_UNAVAILABLE
                    and position.prior_state in {ActiveLifecycleState.LIVE_ACTIVE,
                                                 ActiveLifecycleState.EVENT_UNRESOLVED})))
            if (position.mcx_v1_contract_symbol is None
                    or (not outage_exit and position.state not in {
                        ActiveLifecycleState.LIVE_ACTIVE,
                        ActiveLifecycleState.CLOSED,
                    })
                    or (position.state is not ActiveLifecycleState.CLOSED
                        and position.integrity_hash != expected_hash)
                    or (contract, expiry, lots) != (
                        binding.instrument.trading_symbol,
                        binding.instrument.expiry.isoformat(), position.lots)
                    or sha256(evidence_bytes).hexdigest() != evidence_sha256):
                raise ValueError("MCX_V1_LIVE_EXIT_INPUT_STALE")
            plan_path = (self.plans.root / entry.run_identity / entry.family.value
                         / (entry.plan_id + ".json"))
            plan = self.plans.load(plan_path)
            outcome = self.outcomes.load_for_plan(entry.plan_id)
            if (plan.integrity_hash != position.trade_plan_hash
                    or (entry.model_relation == "SPONSOR_DIRECTED_OUTSIDE_MODEL"
                        and entry.entry_outcome_sha256 is not None)
                    or (entry.model_relation != "SPONSOR_DIRECTED_OUTSIDE_MODEL"
                        and (outcome is None or
                             entry.entry_outcome_sha256 != outcome.integrity_sha256))):
                raise ValueError("MCX_V1_LIVE_EXIT_HISTORY_CHANGED")
            if entry.model_relation == "SPONSOR_DIRECTED_OUTSIDE_MODEL":
                outcome = None
            retained_exit = self.live_attestations.root / (position_id + ".exit.json")
            if retained_exit.is_symlink():
                raise ValueError("MCX_V1_LIVE_EXIT_HISTORY_CHANGED")
            if retained_exit.exists():
                attestation = self.live_attestations.load_exit(position_id)
                if (attestation.fill_price != fill_price
                        or attestation.fill_at != fill_at
                        or attestation.broker_evidence_id != evidence_id
                        or attestation.broker_evidence_sha256 != evidence_sha256
                        or attestation.contract_symbol != contract
                        or attestation.expiry != expiry
                        or attestation.lots != lots):
                    raise ValueError("MCX_V1_LIVE_EXIT_REPLAY_CONFLICT")
            else:
                attestation = McxLiveFillAttestation.create(
                    plan, contract_symbol=contract, expiry=expiry, lots=lots,
                    provider_order_quantity=None, entry_outcome=outcome,
                    fill_price=fill_price, fill_at=fill_at,
                    broker_evidence_id=evidence_id,
                    broker_evidence_sha256=evidence_sha256,
                    attested_at=attested_at, v1_manual=True)
            return self.live_exit(
                position_id, expected_hash, attestation, evidence_bytes, reason)
